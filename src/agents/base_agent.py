"""
Agent 基类 - 所有 Agent 的公共接口和能力
"""
import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None  # 允许无 anthropic 库运行（Mock 模式）

from src.config.settings import ANTHROPIC_API_KEY, LLM_CONFIG
from src.utils.database import log_agent_run, complete_agent_run


@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    description: str
    input_schema: dict


@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    data: Any = None
    error: Optional[str] = None


@dataclass
class AgentRunContext:
    """Agent 运行上下文"""
    run_id: int = 0
    started_at: float = 0
    total_tokens: int = 0
    total_cost: float = 0
    steps: list = field(default_factory=list)


class BaseAgent(ABC):
    """
    Agent 基类

    提供：
    - LLM 调用（Claude API with function calling）
    - 工具注册和调度
    - 运行日志记录
    - 成本追踪
    """

    def __init__(self, name: str, system_prompt: str):
        self.name = name
        self.system_prompt = system_prompt
        self.client = Anthropic(api_key=ANTHROPIC_API_KEY) if (Anthropic and ANTHROPIC_API_KEY) else None
        self.tools: Dict[str, callable] = {}
        self.tool_definitions: List[dict] = []
        self._register_tools()

    @abstractmethod
    def _register_tools(self):
        """子类实现：注册可用工具"""
        pass

    @abstractmethod
    def run(self, task: str, **kwargs) -> dict:
        """子类实现：执行任务"""
        pass

    def register_tool(self, name: str, description: str,
                      input_schema: dict, handler: callable):
        """注册一个工具"""
        self.tools[name] = handler
        self.tool_definitions.append({
            "name": name,
            "description": description,
            "input_schema": input_schema,
        })

    def call_llm(self, messages: List[dict], model: str = None,
                 max_tokens: int = None, use_tools: bool = True) -> dict:
        """
        调用 Claude API

        Args:
            messages: 对话历史
            model: 模型名称
            max_tokens: 最大输出 token
            use_tools: 是否启用 function calling

        Returns:
            API 响应
        """
        if not self.client:
            return self._mock_llm_response(messages)

        kwargs = {
            "model": model or LLM_CONFIG["default_model"],
            "max_tokens": max_tokens or LLM_CONFIG["max_tokens"],
            "system": self.system_prompt,
            "messages": messages,
        }

        if use_tools and self.tool_definitions:
            kwargs["tools"] = self.tool_definitions

        response = self.client.messages.create(**kwargs)
        return response

    def execute_tool(self, tool_name: str, tool_input: dict) -> ToolResult:
        """执行工具调用"""
        handler = self.tools.get(tool_name)
        if not handler:
            return ToolResult(success=False, error=f"Unknown tool: {tool_name}")

        try:
            result = handler(**tool_input)
            return ToolResult(success=True, data=result)
        except Exception as e:
            return ToolResult(success=False, error=str(e))

    def run_agent_loop(self, task: str, max_iterations: int = 10,
                       **kwargs) -> dict:
        """
        ReAct 风格的 Agent 循环

        1. 发送任务给 LLM
        2. LLM 决定调用工具或直接回答
        3. 如果调用工具，执行后将结果反馈给 LLM
        4. 重复直到 LLM 给出最终回答
        """
        ctx = AgentRunContext(
            run_id=log_agent_run(self.name, task[:100], kwargs),
            started_at=time.time(),
        )

        messages = [{"role": "user", "content": task}]
        final_result = None

        for iteration in range(max_iterations):
            print(f"  [{self.name}] Step {iteration + 1}...")

            response = self.call_llm(messages)

            # 检查是否需要调用工具
            if hasattr(response, 'content'):
                tool_calls = [
                    block for block in response.content
                    if hasattr(block, 'type') and block.type == "tool_use"
                ]
                text_blocks = [
                    block for block in response.content
                    if hasattr(block, 'type') and block.type == "text"
                ]
            else:
                tool_calls = []
                text_blocks = []

            if hasattr(response, 'usage'):
                ctx.total_tokens += response.usage.input_tokens + response.usage.output_tokens

            # 如果没有工具调用，说明 LLM 给出了最终回答
            if not tool_calls:
                final_text = ""
                for block in text_blocks:
                    final_text += block.text
                final_result = {"text": final_text, "iterations": iteration + 1}
                break

            # 执行工具调用
            assistant_content = []
            for block in response.content:
                if hasattr(block, 'type'):
                    if block.type == "text":
                        assistant_content.append({"type": "text", "text": block.text})
                    elif block.type == "tool_use":
                        assistant_content.append({
                            "type": "tool_use",
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        })

            messages.append({"role": "assistant", "content": assistant_content})

            # 执行所有工具调用并收集结果
            tool_results = []
            for tc in tool_calls:
                print(f"    Tool: {tc.name}({json.dumps(tc.input, ensure_ascii=False)[:100]}...)")
                result = self.execute_tool(tc.name, tc.input)
                ctx.steps.append({
                    "tool": tc.name,
                    "input": tc.input,
                    "success": result.success,
                })
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": tc.id,
                    "content": json.dumps(
                        result.data if result.success else {"error": result.error},
                        ensure_ascii=False, default=str
                    ),
                })

            messages.append({"role": "user", "content": tool_results})

        # 记录运行完成
        duration = time.time() - ctx.started_at
        cost = self._estimate_cost(ctx.total_tokens)

        complete_agent_run(
            ctx.run_id,
            output_summary=final_result.get("text", "")[:500] if final_result else "Max iterations reached",
            tokens_used=ctx.total_tokens,
            cost_usd=cost,
            duration_seconds=duration,
            status="completed" if final_result else "max_iterations",
        )

        if final_result:
            final_result["tokens_used"] = ctx.total_tokens
            final_result["cost_usd"] = cost
            final_result["duration_seconds"] = round(duration, 2)
            final_result["steps"] = ctx.steps

        return final_result or {"error": "Max iterations reached", "steps": ctx.steps}

    def _estimate_cost(self, tokens: int) -> float:
        """估算 API 成本（Claude Sonnet 定价）"""
        # Sonnet: $3/M input, $15/M output, 粗略按 $9/M 平均
        return tokens * 9.0 / 1_000_000

    def _mock_llm_response(self, messages: list) -> dict:
        """
        无 API Key 时的 Mock 响应，用于开发调试
        """
        print(f"  [{self.name}] [MOCK MODE] No API key, returning mock response")

        @dataclass
        class MockTextBlock:
            type: str = "text"
            text: str = ""

        @dataclass
        class MockUsage:
            input_tokens: int = 0
            output_tokens: int = 0

        @dataclass
        class MockResponse:
            content: list = field(default_factory=list)
            usage: MockUsage = field(default_factory=MockUsage)

        return MockResponse(
            content=[MockTextBlock(
                text="[MOCK] This is a mock response. "
                     "Set ANTHROPIC_API_KEY to enable real LLM calls."
            )],
            usage=MockUsage(input_tokens=100, output_tokens=50),
        )
