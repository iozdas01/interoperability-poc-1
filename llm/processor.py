import json
import openai
from typing import Dict, Any, List, Optional
from pathlib import Path

class LLMProcessor:
    """Centralized LLM interaction manager supporting Text and Vision."""
    
    def __init__(self, model: str = "gpt-4o-mini"):
        self.client = openai.OpenAI()
        self.model = model
        
    def ask_llm(self, 
                prompt: str, 
                system_message: str = "You are a deterministic semantic inference engine. You must return valid JSON only. Do not include explanations or comments If information is missing, return null.”",
                image_base64: Optional[str] = None) -> Dict[str, Any]:
        """
        Send a prompt (optionally with an image) to the LLM and expect a JSON response.
        """
        messages = [
            {"role": "system", "content": system_message}
        ]
        
        if image_base64:
            # Vision content structure
            user_content = [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{image_base64}"}
                }
            ]
        else:
            user_content = prompt

        messages.append({"role": "user", "content": user_content})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.2,
                max_tokens=1000 if image_base64 else 500
            )
            content = response.choices[0].message.content.strip()
            return self._parse_json(content)
        except Exception as e:
            print(f"LLM API Error: {e}")
            return {"error": str(e)}

    def _parse_json(self, content: str) -> Dict[str, Any]:
        """Extract and clean JSON from response text."""
        import re
        try:
            # Remove markdown code blocks
            content = re.sub(r'```(?:json)?', '', content)
            content = re.sub(r'```', '', content)
            content = content.strip()
            
            # Find the first { and last } to isolate the JSON object if there's trailing junk
            start = content.find('{')
            end = content.rfind('}')
            if start != -1 and end != -1:
                content = content[start:end+1]
                
            return json.loads(content)
        except json.JSONDecodeError:
            print(f"Failed to parse JSON response: {content[:100]}...")
            return {"error": "Invalid JSON response", "raw_content": content}
