import json
import openai
from typing import Dict, Any, List
from pathlib import Path

class LLMProcessor:
    """Base class for LLM interactions."""
    
    def __init__(self, model: str = "gpt-4"):
        self.client = openai.OpenAI()
        self.model = model
        
    def ask_llm(self, prompt: str, system_message: str = "You are a helpful assistant.") -> Dict[str, Any]:
        """Send a prompt to the LLM and expect a JSON response."""
        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_message},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.2
            )
            content = response.choices[0].message.content.strip()
            return self._parse_json(content)
        except Exception as e:
            print(f"LLM API Error: {e}")
            return {"error": str(e)}

    def _parse_json(self, content: str) -> Dict[str, Any]:
        """Extract JSON from response text."""
        import re
        try:
            # Try to find JSON block
            match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
            if match:
                return json.loads(match.group(1))
            
            # Try finding raw JSON object
            match = re.search(r'(\{.*\})', content, re.DOTALL)
            if match:
                return json.loads(match.group(1))
                
            return json.loads(content)
        except json.JSONDecodeError:
            print(f"Failed to parse JSON response: {content[:100]}...")
            return {"error": "Invalid JSON response", "raw_content": content}
