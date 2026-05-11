"""
================================================================================
  backend/app/services/vision_service.py  —  DIAGRAM ANALYSIS via GEMINI VISION
================================================================================

PURPOSE:
  The first stage of the pipeline. Takes the uploaded diagram image and uses
  Google Gemini's multimodal vision API to extract a structured JSON description
  of every cloud component, network boundary, and connection it can see.

WHY GEMINI (not Bedrock) for Vision:
  AWS Bedrock Claude does not accept image inputs in the same SDK path.
  Google Gemini's `gemini-2.5-pro` is a top multimodal model and has a
  generous free tier. Vision = Gemini, Text = Claude (Bedrock).

CONNECTIONS TO OTHER FILES:
  • core/config.py         → GEMINI_API_KEY, GEMINI_VISION_MODEL
  • api/v1/jobs.py         → calls analyze_diagram() and stores result in job
  • design_doc_service.py  → receives the analysis dict as `vision_analysis`

DATA FLOW:
  1. jobs.py saves uploaded file to disk (UUID filename in uploads/)
  2. jobs.py calls VisionService.analyze_diagram(image_path)
  3. This service reads the image as bytes
  4. Sends bytes + prompt to Gemini via google.genai SDK
  5. Parses JSON from Gemini's text response
  6. Returns {success, analysis{components, connections, boundaries}, raw_response}
  7. jobs.py stores result in _jobs[job_id] as `vision_analysis`

OUTPUT SHAPE:
  {
    "components":  [{name, type, provider, configuration, confidence}, ...]
    "connections": [{source, target, protocol, port, type}, ...]
    "boundaries":  [{type, name, cidr, region}, ...]
    "metadata":    {regions, environments, cidrs}
  }
================================================================================
"""

import json
import re
import logging
from google import genai
from google.genai import types
from PIL import Image
from typing import Dict, List, Any
from pathlib import Path
from app.core.config import settings

logger = logging.getLogger(__name__)


class VisionService:
    """Gemini Vision service for analyzing architecture diagrams.

    Uses the google.genai SDK (not deprecated google.generativeai).
    Initialized once per app worker process (singleton pattern in jobs.py).
    """
    
    def __init__(self):
        self.client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self.model_name = settings.GEMINI_VISION_MODEL
        logger.info(f"[VisionService] Initialized with model: {self.model_name}")
    
    def analyze_diagram(self, image_path: str, ocr_text: str = None) -> Dict:
        """Analyze architecture diagram using Gemini Vision"""
        logger.info(f"[VisionService] Analyzing diagram: {image_path}")
        try:
            # Load image as bytes for the new SDK
            image_bytes = Path(image_path).read_bytes()
            logger.info(f"[VisionService] Loaded image: {len(image_bytes)} bytes")
            
            # Build prompt for architecture analysis
            prompt = self._build_analysis_prompt(ocr_text)
            
            # Generate response using new SDK
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Content(parts=[
                        types.Part.from_text(text=prompt),
                        types.Part.from_bytes(data=image_bytes, mime_type=self._get_mime_type(image_path)),
                    ])
                ]
            )
            
            # Parse response
            response_text = response.text
            logger.info(f"[VisionService] Gemini response received: {len(response_text)} chars")
            analysis = self._parse_vision_response(response_text)
            logger.info(f"[VisionService] Parsed {len(analysis.get('components', []))} components, {len(analysis.get('connections', []))} connections")
            
            return {
                "success": True,
                "analysis": analysis,
                "raw_response": response_text
            }
        except Exception as e:
            logger.error(f"Vision analysis failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "analysis": {}
            }
    
    @staticmethod
    def _get_mime_type(image_path: str) -> str:
        """Determine MIME type from file extension."""
        ext = Path(image_path).suffix.lower()
        mime_map = {
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".svg": "image/svg+xml",
            ".pdf": "application/pdf",
        }
        return mime_map.get(ext, "image/png")
    
    def _build_analysis_prompt(self, ocr_text: str = None) -> str:
        """Build detailed prompt for architecture analysis"""
        
        prompt = """You are an expert cloud infrastructure architect. Analyze this architecture diagram and extract structured information.

Please identify and extract:
1. Cloud provider(s): AWS, GCP, Azure, or multi-cloud
2. Services and components: EC2, S3, RDS, Lambda, etc.
3. Network boundaries: VPCs, subnets, regions, availability zones
4. Connections and data flows: arrows, lines between components
5. Labels and annotations: text labels on components
6. Ports and protocols: if visible (e.g., :80, :443, tcp, https)
7. Environments: dev, prod, staging
8. Regions: if specified
9. CIDR blocks: network ranges if visible

Return your analysis as structured JSON with the following format:
{
  "cloud_providers": [{"provider": "aws/gcp/azure", "confidence": 0.0-1.0, "evidence": ["reason1", "reason2"]}],
  "components": [{"name": "component_name", "type": "service_type", "provider": "aws/gcp/azure", "configuration": {}, "labels": [], "ports": [], "confidence": 0.0-1.0}],
  "boundaries": [{"type": "vpc/subnet/region/az", "name": "boundary_name", "provider": "aws/gcp/azure", "cidr": "10.0.0.0/16", "region": "us-east-1"}],
  "connections": [{"source": "component1", "target": "component2", "protocol": "tcp/https", "port": 443, "type": "synchronous/asynchronous"}],
  "metadata": {"regions": [], "environments": [], "cidrs": []},
  "unresolved": [{"item": "unclear_element", "ambiguity": "description", "possible_interpretations": []}]
}

Be thorough and precise. If something is unclear, mark it as unresolved."""
        
        if ocr_text:
            prompt += f"\n\nOCR extracted text from the image:\n{ocr_text}\n\nUse this OCR text to supplement your visual analysis, but prioritize the visual diagram structure."
        
        return prompt
    
    def _parse_vision_response(self, response_text: str) -> Dict:
        """Parse Gemini Vision response into structured format"""
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', response_text)
            
            if json_match:
                json_str = json_match.group()
                analysis = json.loads(json_str)
                return analysis
            else:
                # Fallback: parse text manually
                return self._parse_text_response(response_text)
                
        except Exception as e:
            return {
                "error": f"Failed to parse response: {str(e)}",
                "raw_text": response_text
            }
    
    def _parse_text_response(self, text: str) -> Dict:
        """Fallback text parser when JSON extraction fails"""
        # Simple keyword extraction
        analysis = {
            "cloud_providers": [],
            "components": [],
            "boundaries": [],
            "connections": [],
            "metadata": {"regions": [], "environments": [], "cidrs": []},
            "unresolved": []
        }
        
        text_lower = text.lower()
        
        # Detect cloud providers
        if "aws" in text_lower or "amazon" in text_lower:
            analysis["cloud_providers"].append({"provider": "aws", "confidence": 0.8})
        if "gcp" in text_lower or "google" in text_lower:
            analysis["cloud_providers"].append({"provider": "gcp", "confidence": 0.8})
        if "azure" in text_lower or "microsoft" in text_lower:
            analysis["cloud_providers"].append({"provider": "azure", "confidence": 0.8})
        
        return analysis
    
    def extract_components_with_bounding_boxes(self, image_path: str) -> List[Dict]:
        """Extract components with their visual bounding boxes"""
        try:
            image_bytes = Path(image_path).read_bytes()
            prompt = """Identify all components in this architecture diagram. For each component, provide:
            - Component name/type
            - Approximate bounding box (x, y, width, height as percentages)
            - Cloud provider
            
            Return as JSON list."""
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Content(parts=[
                        types.Part.from_text(text=prompt),
                        types.Part.from_bytes(data=image_bytes, mime_type=self._get_mime_type(image_path)),
                    ])
                ]
            )
            
            json_match = re.search(r'\[[\s\S]*\]', response.text)
            if json_match:
                return json.loads(json_match.group())
            return []
        except Exception as e:
            logger.warning(f"Bounding box extraction failed: {e}")
            return []
    
    def detect_connections(self, image_path: str, components: List[Dict]) -> List[Dict]:
        """Detect connections between components"""
        prompt = f"""Analyze the connections and data flows in this architecture diagram.

Known components:
{', '.join([c.get('name', c.get('type', 'unknown')) for c in components])}

For each connection, identify:
- Source component
- Target component
- Type of connection (synchronous, asynchronous, pub/sub, etc.)
- Protocol if visible (HTTP, TCP, etc.)
- Port if visible

Return as JSON list."""
        
        try:
            image_bytes = Path(image_path).read_bytes()
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[
                    types.Content(parts=[
                        types.Part.from_text(text=prompt),
                        types.Part.from_bytes(data=image_bytes, mime_type=self._get_mime_type(image_path)),
                    ])
                ]
            )
            
            json_match = re.search(r'\[[\s\S]*\]', response.text)
            if json_match:
                return json.loads(json_match.group())
            return []
        except Exception as e:
            logger.warning(f"Connection detection failed: {e}")
            return []
