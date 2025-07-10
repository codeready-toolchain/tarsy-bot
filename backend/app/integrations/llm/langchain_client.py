"""
Simplified LLM client using LangChain's interfaces and prompt templates.
Focuses on core functionality needed for SRE agent operations.
"""

import json
import time
from typing import Dict, List, Optional, Any
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.prompts import ChatPromptTemplate, SystemMessagePromptTemplate, HumanMessagePromptTemplate
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_openai import ChatOpenAI
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_xai import ChatXAI

from app.config.settings import Settings
from app.models.alert import Alert
from app.utils.logger import get_module_logger

logger = get_module_logger(__name__)


class LangChainLLMClient:
    """Simplified LLM client using LangChain abstractions."""
    
    def __init__(self, settings: Settings):
        self.settings = settings
        self.llm_models: Dict[str, BaseChatModel] = {}
        self.default_provider = settings.default_llm_provider
        self._initialize_models()
        self._create_prompt_templates()
    
    def _initialize_models(self):
        """Initialize all configured LLM models."""
        logger.info(f"Initializing LLM models with default provider: {self.default_provider}")
        
        for provider in self.settings.llm_providers.keys():
            try:
                # Use get_llm_config to get the configuration with actual API key
                config = self.settings.get_llm_config(provider)
                
                if not config.get("api_key"):
                    logger.warning(f"No API key configured for {provider}")
                    continue
                
                if provider == "openai":
                    self.llm_models[provider] = ChatOpenAI(
                        model=config.get("model", "gpt-4-1106-preview"),
                        api_key=config["api_key"],
                        temperature=config.get("temperature", 0.3)
                    )
                elif provider == "gemini":
                    self.llm_models[provider] = ChatGoogleGenerativeAI(
                        model=config.get("model", "gemini-pro"),
                        google_api_key=config["api_key"],
                        temperature=config.get("temperature", 0.3)
                    )
                elif provider == "grok":
                    self.llm_models[provider] = ChatXAI(
                        model=config.get("model", "grok-beta"),
                        api_key=config["api_key"],
                        temperature=config.get("temperature", 0.3)
                    )
                
                logger.info(f"Initialized LLM model: {provider}")
            except Exception as e:
                logger.error(f"Failed to initialize {provider}: {str(e)}")
        
        if not self.llm_models:
            logger.error("No LLM models were successfully initialized! Check your configuration and API keys.")
        else:
            logger.info(f"Successfully initialized {len(self.llm_models)} LLM models: {list(self.llm_models.keys())}")
    
    def _create_prompt_templates(self):
        """Create prompt templates for different use cases."""
        # System prompt for SRE analysis
        self.system_prompt = SystemMessagePromptTemplate.from_template(
            """You are an expert SRE (Site Reliability Engineer) with deep knowledge of:
            - Kubernetes and container orchestration
            - Cloud infrastructure (AWS, GCP, Azure)
            - Monitoring and observability tools
            - Incident response and troubleshooting
            - Infrastructure as Code
            - Distributed systems architecture
            
            Your role is to analyze system alerts and provide actionable insights based on:
            1. The alert information
            2. Available runbook procedures
            3. System data gathered from monitoring tools
            
            Always provide:
            - Root cause analysis
            - Immediate remediation steps
            - Prevention recommendations
            - Risk assessment
            
            Be concise but thorough in your analysis."""
        )
        
        # Template for alert analysis
        self.alert_analysis_template = ChatPromptTemplate.from_messages([
            self.system_prompt,
            HumanMessagePromptTemplate.from_template(
                """Alert Information:
                {alert_info}
                
                Runbook Information:
                {runbook_info}
                
                System Data:
                {system_data}
                
                Please provide a comprehensive analysis of this alert including:
                1. Root cause analysis
                2. Immediate action items
                3. Prevention strategies
                4. Risk assessment
                
                Analysis:"""
            )
        ])
        
        # Template for determining next steps
        self.next_steps_template = ChatPromptTemplate.from_messages([
            self.system_prompt,
            HumanMessagePromptTemplate.from_template(
                """Based on the current alert and investigation progress, determine what additional data needs to be gathered.
                
                Alert: {alert_info}
                Available Tools: {available_tools}
                Investigation History: {investigation_history}
                
                Should we continue gathering data? If yes, which tools should be used and why?
                If no, explain why we have sufficient information.
                
                Respond in JSON format:
                {{
                    "continue": true/false,
                    "reasoning": "explanation of decision",
                    "tools": [
                        {{
                            "server": "server_name",
                            "tool": "tool_name",
                            "parameters": {{"param": "value"}},
                            "reason": "why this tool is needed"
                        }}
                    ]
                }}"""
            )
        ])
        
        # Template for partial analysis
        self.partial_analysis_template = ChatPromptTemplate.from_messages([
            self.system_prompt,
            HumanMessagePromptTemplate.from_template(
                """Provide a brief analysis of the data gathered in this iteration.
                
                Alert: {alert_info}
                Current Data: {current_data}
                
                Summarize what this data tells us about the alert and what insights we've gained.
                Keep it concise (2-3 sentences).
                
                Analysis:"""
            )
        ])
    
    def get_model(self, provider: Optional[str] = None) -> Optional[BaseChatModel]:
        """Get a specific LLM model or the default one."""
        if provider and provider in self.llm_models:
            return self.llm_models[provider]
        elif self.default_provider in self.llm_models:
            return self.llm_models[self.default_provider]
        elif self.llm_models:
            return next(iter(self.llm_models.values()))
        return None
    
    def _log_llm_interaction(self, provider: str, method: str, prompt: str, response: str, duration: float, error: Optional[str] = None):
        """Log LLM interactions with detailed information."""
        interaction_data = {
            "timestamp": time.time(),
            "provider": provider,
            "method": method,
            "duration_seconds": round(duration, 3),
            "prompt_length": len(prompt),
            "response_length": len(response) if response else 0,
            "status": "error" if error else "success"
        }
        
        if error:
            interaction_data["error"] = error
        
        # Log the interaction summary
        logger.info(f"LLM Communication - {provider} ({method}): {interaction_data['status']} in {duration:.3f}s")
        
        # Log detailed prompt (truncated for readability)
        prompt_preview = prompt[:500] + "..." if len(prompt) > 500 else prompt
        logger.debug(f"LLM Request to {provider}:\n{prompt_preview}")
        
        # Log detailed response (truncated for readability)
        if response:
            response_preview = response[:500] + "..." if len(response) > 500 else response
            logger.debug(f"LLM Response from {provider}:\n{response_preview}")
        
        # Log full interaction data as JSON for potential analysis
        logger.info(f"LLM Interaction Data: {json.dumps(interaction_data, indent=2)}")
    
    def _safe_invoke_llm(self, model: BaseChatModel, prompt: str, provider: str, method: str) -> str:
        """Safely invoke LLM with comprehensive logging."""
        start_time = time.time()
        
        try:
            logger.info(f"Invoking {provider} LLM for {method}")
            logger.debug(f"Full prompt for {provider}:\n{prompt}")
            
            response = model.invoke(prompt)
            duration = time.time() - start_time
            
            response_content = response.content if hasattr(response, 'content') else str(response)
            
            # Log successful interaction
            self._log_llm_interaction(provider, method, prompt, response_content, duration)
            
            return response_content
            
        except Exception as e:
            duration = time.time() - start_time
            error_msg = str(e)
            
            # Log failed interaction
            self._log_llm_interaction(provider, method, prompt, "", duration, error_msg)
            
            logger.error(f"LLM invocation failed for {provider} ({method}): {error_msg}")
            raise
    
    async def _safe_ainvoke_llm(self, model: BaseChatModel, prompt: str, provider: str, method: str) -> str:
        """Safely invoke LLM asynchronously with comprehensive logging."""
        start_time = time.time()
        
        try:
            logger.info(f"Async invoking {provider} LLM for {method}")
            logger.debug(f"Full prompt for {provider}:\n{prompt}")
            
            response = await model.ainvoke(prompt)
            duration = time.time() - start_time
            
            response_content = response.content if hasattr(response, 'content') else str(response)
            
            # Log successful interaction
            self._log_llm_interaction(provider, method, prompt, response_content, duration)
            
            return response_content
            
        except Exception as e:
            duration = time.time() - start_time
            error_msg = str(e)
            
            # Log failed interaction
            self._log_llm_interaction(provider, method, prompt, "", duration, error_msg)
            
            logger.error(f"LLM async invocation failed for {provider} ({method}): {error_msg}")
            raise

    async def analyze_alert(self, alert: Alert, runbook_data: Dict, system_data: Dict, provider: Optional[str] = None) -> str:
        """Analyze an alert using the configured LLM."""
        model = self.get_model(provider)
        if not model:
            effective_provider = provider or self.default_provider
            available_providers = list(self.llm_models.keys())
            raise Exception(
                f"No LLM model available for provider: {effective_provider}. "
                f"Available providers: {available_providers}. "
                f"Check your API key configuration."
            )
        
        # Prepare the prompt
        prompt = self.alert_analysis_template.format(
            alert_info=self._format_alert_info(alert),
            runbook_info=self._format_runbook_info(runbook_data),
            system_data=self._format_system_data(system_data)
        )
        
        effective_provider = provider or self.default_provider
        logger.info(f"Starting alert analysis with {effective_provider}")
        
        try:
            response = await self._safe_ainvoke_llm(model, prompt, effective_provider, "analyze_alert")
            logger.info(f"Alert analysis completed successfully with {effective_provider}")
            return response
        except Exception as e:
            logger.error(f"Alert analysis failed with {effective_provider}: {str(e)}")
            raise
    
    async def determine_next_steps(self, alert: Alert, available_tools: Dict, investigation_history: List[Dict], provider: Optional[str] = None) -> Dict:
        """Determine what tools to use next in the investigation."""
        model = self.get_model(provider)
        if not model:
            effective_provider = provider or self.default_provider
            available_providers = list(self.llm_models.keys())
            raise Exception(
                f"No LLM model available for provider: {effective_provider}. "
                f"Available providers: {available_providers}. "
                f"Check your API key configuration."
            )
        
        # Prepare the prompt
        prompt = self.next_steps_template.format(
            alert_info=self._format_alert_info(alert),
            available_tools=self._format_available_tools(available_tools),
            investigation_history=self._format_investigation_history(investigation_history)
        )
        
        effective_provider = provider or self.default_provider
        logger.info(f"Determining next steps with {effective_provider}")
        
        try:
            response = await self._safe_ainvoke_llm(model, prompt, effective_provider, "determine_next_steps")
            
            # Parse JSON response
            try:
                parsed_response = json.loads(response)
                logger.info(f"Next steps determination completed successfully with {effective_provider}")
                logger.debug(f"Parsed next steps response: {json.dumps(parsed_response, indent=2)}")
                return parsed_response
            except json.JSONDecodeError as json_error:
                logger.error(f"Failed to parse JSON response from {effective_provider}: {str(json_error)}")
                logger.debug(f"Raw response that failed to parse: {response}")
                # Return fallback
                return {
                    "continue": False,
                    "reasoning": f"Error parsing LLM response: {str(json_error)}",
                    "tools": []
                }
            
        except Exception as e:
            logger.error(f"Next steps determination failed with {effective_provider}: {str(e)}")
            # Return fallback
            return {
                "continue": False,
                "reasoning": f"Error determining next steps: {str(e)}",
                "tools": []
            }
    
    async def analyze_partial_results(self, alert: Alert, current_data: Dict, provider: Optional[str] = None) -> str:
        """Analyze partial results from current iteration."""
        model = self.get_model(provider)
        if not model:
            effective_provider = provider or self.default_provider
            available_providers = list(self.llm_models.keys())
            raise Exception(
                f"No LLM model available for provider: {effective_provider}. "
                f"Available providers: {available_providers}. "
                f"Check your API key configuration."
            )
        
        # Prepare the prompt
        prompt = self.partial_analysis_template.format(
            alert_info=self._format_alert_info(alert),
            current_data=self._format_system_data(current_data)
        )
        
        effective_provider = provider or self.default_provider
        logger.info(f"Starting partial results analysis with {effective_provider}")
        
        try:
            response = await self._safe_ainvoke_llm(model, prompt, effective_provider, "analyze_partial_results")
            logger.info(f"Partial results analysis completed successfully with {effective_provider}")
            return response
        except Exception as e:
            logger.error(f"Partial analysis failed with {effective_provider}: {str(e)}")
            return f"Error analyzing partial results: {str(e)}"
    
    def _format_alert_info(self, alert: Alert) -> str:
        """Format alert information for prompts."""
        return f"""Alert: {alert.alert}
Severity: {alert.severity}
Environment: {alert.environment}
Cluster: {alert.cluster}
Namespace: {alert.namespace}
Pod: {alert.pod}
Message: {alert.message}
Runbook: {alert.runbook}"""
    
    def _format_runbook_info(self, runbook_data: Dict) -> str:
        """Format runbook information for prompts."""
        return runbook_data.get("raw_content", "No runbook content available")
    
    def _format_system_data(self, system_data: Dict) -> str:
        """Format system data for prompts."""
        if not system_data:
            return "No system data available"
        
        formatted = []
        for source, data in system_data.items():
            formatted.append(f"=== {source.upper()} ===")
            if isinstance(data, list):
                for item in data:
                    formatted.append(str(item))
            else:
                formatted.append(str(data))
            formatted.append("")
        
        return "\n".join(formatted)
    
    def _format_available_tools(self, available_tools: Dict) -> str:
        """Format available tools for prompts."""
        if not available_tools:
            return "No tools available"
        
        formatted = []
        for server, tools in available_tools.items():
            formatted.append(f"Server: {server}")
            for tool in tools:
                formatted.append(f"  - {tool.get('name', 'Unknown')}: {tool.get('description', 'No description')}")
        
        return "\n".join(formatted)
    
    def _format_investigation_history(self, history: List[Dict]) -> str:
        """Format investigation history for prompts."""
        if not history:
            return "No investigation history"
        
        formatted = []
        for i, iteration in enumerate(history, 1):
            formatted.append(f"Iteration {i}:")
            formatted.append(f"  Reasoning: {iteration.get('reasoning', 'No reasoning')}")
            formatted.append(f"  Tools used: {len(iteration.get('tools_called', []))}")
            if iteration.get('partial_analysis'):
                formatted.append(f"  Analysis: {iteration['partial_analysis']}")
        
        return "\n".join(formatted)
    
    def list_available_providers(self) -> List[str]:
        """List available LLM providers."""
        return list(self.llm_models.keys()) 