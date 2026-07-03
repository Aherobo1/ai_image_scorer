import os
import logging
from typing import Dict, Tuple, Optional
from google.cloud import vision
import google.generativeai as genai
from PIL import Image
import io
from dotenv import load_dotenv

load_dotenv()

# Set up logging
logger = logging.getLogger(__name__)

class ContentModerator:
    """
    Content Safety & Moderation using Gemini AI (primary) and Google Vision (fallback)
    Detects inappropriate content before image scoring
    """
    
    def __init__(self):
        """Initialize the content moderator with Gemini and Google Vision"""
        logger.info("Initializing ContentModerator...")
        
        # Initialize Gemini (Primary method)
        self.gemini_enabled = False
        gemini_key = os.getenv('GEMINI_API_KEY')
        if gemini_key:
            try:
                genai.configure(api_key=gemini_key)
                self.gemini_model = genai.GenerativeModel('gemini-2.5-flash')
                self.gemini_enabled = True
                logger.info("Gemini AI initialized successfully (PRIMARY moderation method)")
            except Exception as e:
                logger.warning(f"Failed to initialize Gemini: {e}")
                self.gemini_enabled = False
        
        # Initialize Google Cloud Vision (Fallback/OCR method)
        self.vision_enabled = False
        credentials_path = os.getenv('GOOGLE_APPLICATION_CREDENTIALS')
        if credentials_path:
            try:
                self.vision_client = vision.ImageAnnotatorClient()
                self.vision_enabled = True
                logger.info("Google Cloud Vision initialized successfully (FALLBACK for OCR/object detection)")
            except Exception as e:
                logger.warning(f"Failed to initialize Google Cloud Vision: {e}")
                self.vision_enabled = False
        
        # Set moderation status
        self.moderation_enabled = self.gemini_enabled or self.vision_enabled
        
        if not self.moderation_enabled:
            logger.warning("⚠️  NO moderation methods available! All content will be allowed.")
        elif self.gemini_enabled:
            logger.info("✅ Content moderation ready: Using Gemini AI (primary)")
        elif self.vision_enabled:
            logger.info("✅ Content moderation ready: Using Google Vision (fallback)")
    
    def check_content_safety(self, image_path: str) -> Tuple[bool, Dict]:
        """
        Check if image content is safe for processing
        Primary: Gemini AI
        Fallback: Google Cloud Vision
        
        Returns:
            Tuple[bool, Dict]: (is_safe, moderation_details)
        """
        logger.info(f"Starting content safety check for: {image_path}")
        
        if not self.moderation_enabled:
            logger.warning("Content moderation disabled - skipping safety check")
            return True, {"status": "moderation_disabled", "reason": "No moderation services configured"}
        
        # Try Gemini first (primary method)
        if self.gemini_enabled:
            try:
                return self._check_with_gemini(image_path)
            except Exception as e:
                logger.error(f"Gemini moderation failed: {e}")
                # Fall through to Google Vision if available
        
        # Fallback to Google Vision
        if self.vision_enabled:
            try:
                return self._check_with_google_vision(image_path)
            except Exception as e:
                logger.error(f"Google Vision moderation failed: {e}")
        
        # If all methods fail, allow content but log error
        logger.error("All moderation methods failed - allowing content by default")
        return True, {
            "status": "error",
            "error": "All moderation methods failed",
            "is_safe": True,
            "rejection_reason": None
        }
    
    def _check_with_gemini(self, image_path: str) -> Tuple[bool, Dict]:
        """Check content safety using Gemini AI"""
        logger.info("Using Gemini AI for content moderation...")
        
        # Load image and convert to RGB if needed (handles .mpo and other formats)
        img = Image.open(image_path)
        
        # Convert to RGB if necessary (handles RGBA, P, L, CMYK, MPO, etc.)
        if img.mode not in ('RGB', 'JPEG'):
            logger.info(f"Converting image from {img.mode} to RGB for Gemini compatibility")
            img = img.convert('RGB')
        
        # For unsupported formats like .mpo, save as JPEG temporarily
        if image_path.lower().endswith('.mpo') or img.format == 'MPO':
            logger.info("Detected .mpo format - converting to JPEG for Gemini")
            temp_path = image_path.rsplit('.', 1)[0] + '_temp.jpg'
            img.save(temp_path, 'JPEG', quality=95)
            img = Image.open(temp_path)
            logger.info("Image converted to JPEG successfully")
        
        # Create prompt for safety analysis
        prompt = """Analyze this image for content safety. Rate on a scale of 1-5:
        1 = VERY_UNLIKELY
        2 = UNLIKELY
        3 = POSSIBLE
        4 = LIKELY
        5 = VERY_LIKELY
        
        Provide scores for:
        - Adult (explicit sexual content)
        - Racy (suggestive, revealing)
        - Violence (graphic violence)
        
        Format EXACTLY:
        Adult: [score]
        Racy: [score]
        Violence: [score]
        
        Then briefly explain your reasoning."""
        
        response = self.gemini_model.generate_content([prompt, img])
        response_text = response.text
        
        logger.info(f"Gemini response: {response_text[:200]}")
        
        # Parse response
        adult_score = self._extract_score(response_text, "Adult")
        racy_score = self._extract_score(response_text, "Racy")
        violence_score = self._extract_score(response_text, "Violence")
        
        logger.info(f"Gemini scores - Adult: {adult_score}, Racy: {racy_score}, Violence: {violence_score}")
        
        # Apply thresholds (same as before)
        violations = []
        rejection_reason = None
        
        if adult_score >= 3:  # POSSIBLE or higher
            violations.append(f"Adult content (score: {adult_score})")
            rejection_reason = "Contains inappropriate adult content"
        
        if racy_score >= 4:  # LIKELY or VERY_LIKELY
            violations.append(f"Racy content (score: {racy_score})")
            rejection_reason = "Contains suggestive or racy content"
        
        if violence_score >= 4:  # LIKELY or VERY_LIKELY
            violations.append(f"Violence (score: {violence_score})")
            rejection_reason = "Contains violent or graphic content"
        
        is_safe = len(violations) == 0
        
        logger.info(f"Gemini moderation result: {'SAFE' if is_safe else 'BLOCKED'}")
        
        return is_safe, {
            "is_safe": is_safe,
            "rejection_reason": rejection_reason,
            "violations": violations,
            "risk_scores": {
                "adult": adult_score,
                "racy": racy_score,
                "violence": violence_score,
                "medical": 0,
                "spoof": 0
            },
            "method": "gemini",
            "status": "completed"
        }
    
    def _check_with_google_vision(self, image_path: str) -> Tuple[bool, Dict]:
        """Check content safety using Google Cloud Vision (fallback)"""
        logger.info("Using Google Vision for content moderation (fallback)...")
        
        # Load image
        with open(image_path, 'rb') as image_file:
            content = image_file.read()
        
        image = vision.Image(content=content)
        response = self.vision_client.safe_search_detection(image=image)
        safe_search = response.safe_search_annotation
        
        # Analyze results
        moderation_result = self._analyze_safe_search_results(safe_search)
        is_safe = moderation_result['is_safe']
        
        logger.info(f"Google Vision moderation result: {'SAFE' if is_safe else 'BLOCKED'}")
        
        moderation_result['method'] = 'google_vision'
        return is_safe, moderation_result
    
    def _extract_score(self, text: str, category: str) -> int:
        """Extract score from Gemini response"""
        try:
            # Look for pattern like "Adult: 3" or "Adult: POSSIBLE"
            import re
            pattern = rf"{category}:\s*(\d+)"
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                return int(match.group(1))
            
            # Fallback: look for likelihood names
            likelihood_map = {
                'VERY_UNLIKELY': 1,
                'UNLIKELY': 2,
                'POSSIBLE': 3,
                'LIKELY': 4,
                'VERY_LIKELY': 5
            }
            
            for name, score in likelihood_map.items():
                if name.lower() in text.lower():
                    return score
            
            # Default to safe
            return 1
        except:
            return 1
    
    def _analyze_safe_search_results(self, safe_search) -> Dict:
        """
        Analyze Google Cloud Vision SafeSearch results
        
        Returns:
            Dict: Detailed moderation analysis
        """
        # Define risk levels - using the correct API structure
        risk_levels = {
            vision.Likelihood.UNKNOWN: 0,
            vision.Likelihood.VERY_UNLIKELY: 1,
            vision.Likelihood.UNLIKELY: 2,
            vision.Likelihood.POSSIBLE: 3,
            vision.Likelihood.LIKELY: 4,
            vision.Likelihood.VERY_LIKELY: 5
        }
        
        # Get risk scores
        adult_risk = risk_levels.get(safe_search.adult, 0)
        violence_risk = risk_levels.get(safe_search.violence, 0)
        racy_risk = risk_levels.get(safe_search.racy, 0)
        medical_risk = risk_levels.get(safe_search.medical, 0)
        spoof_risk = risk_levels.get(safe_search.spoof, 0)
        
        # Define thresholds for rejection
        # Updated based on testing: Allow model to distinguish borderline vs inappropriate
        REJECTION_THRESHOLDS = {
            'adult': 3,      # POSSIBLE or higher - Explicit sexual content
            'violence': 4,   # LIKELY or VERY_LIKELY - Graphic violence
            'racy': 4,       # LIKELY or VERY_LIKELY - Distinguishes shirtless (3) from exposed (5)
            'medical': 4,    # LIKELY or VERY_LIKELY - Medical/graphic content
            'spoof': 4       # LIKELY or VERY_LIKELY - Manipulated content
        }
        
        # Check for violations
        violations = []
        rejection_reason = None
        
        if adult_risk >= REJECTION_THRESHOLDS['adult']:
            violations.append(f"Adult content (risk level: {adult_risk})")
            rejection_reason = "Contains inappropriate adult content"
        
        if violence_risk >= REJECTION_THRESHOLDS['violence']:
            violations.append(f"Violence (risk level: {violence_risk})")
            rejection_reason = "Contains violent or graphic content"
        
        if racy_risk >= REJECTION_THRESHOLDS['racy']:
            violations.append(f"Racy content (risk level: {racy_risk})")
            rejection_reason = "Contains suggestive or racy content"
        
        if medical_risk >= REJECTION_THRESHOLDS['medical']:
            violations.append(f"Medical content (risk level: {medical_risk})")
            rejection_reason = "Contains medical or graphic content"
        
        if spoof_risk >= REJECTION_THRESHOLDS['spoof']:
            violations.append(f"Spoof content (risk level: {spoof_risk})")
            rejection_reason = "Contains spoof or manipulated content"
        
        # Determine if content is safe
        is_safe = len(violations) == 0
        
        return {
            "is_safe": is_safe,
            "rejection_reason": rejection_reason,
            "violations": violations,
            "risk_scores": {
                "adult": adult_risk,
                "violence": violence_risk,
                "racy": racy_risk,
                "medical": medical_risk,
                "spoof": spoof_risk
            },
            "risk_levels": {
                "adult": str(safe_search.adult),
                "violence": str(safe_search.violence),
                "racy": str(safe_search.racy),
                "medical": str(safe_search.medical),
                "spoof": str(safe_search.spoof)
            },
            "status": "completed"
        }
    
    def get_moderation_status(self) -> Dict:
        """Get the current moderation system status"""
        return {
            "moderation_enabled": self.moderation_enabled,
            "gemini_enabled": self.gemini_enabled,
            "vision_enabled": self.vision_enabled,
            "primary_method": "gemini" if self.gemini_enabled else ("google_vision" if self.vision_enabled else "none")
        }
