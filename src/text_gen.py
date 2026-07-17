import os
import json
import requests
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Validity check for emotion 
VALID_EMOTIONS = ["neutral", "happy", "sad", "angry", "surprised", "scared", "disgust"]

# Paths for config files
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE_DIR, "config", "text_gen.json")
EMOTION_JSON_PATH = os.path.join(BASE_DIR, "config", "emotion.json")

def load_config():
    """Loads the text generation configuration."""
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r") as f:
            return json.load(f)
    return {"model": "phi3", "api_url": "http://localhost:11434/api/generate"}

def generate_response(user_input):
    """
    Calls the local LLM (Ollama) to generate a response in JSON format containing
    the emotion, intensity, and spoken text. Updates the emotion.json file for the
    face renderer, and returns just the text to be spoken.
    """
    config = load_config()
    
    system_prompt = (
    "You are an expressive AI robot. "
    "You must respond in exactly one JSON object. "
    "The JSON must have three keys: 'emotion' (string), 'intensity' (float from 0.0 to 1.0), and 'text' (string). "
    f"The 'emotion' value MUST be exactly one of these words, spelled exactly as shown: {', '.join(VALID_EMOTIONS)}. "
    "Do not use any other word, synonym, or noun form (for example, use 'surprised', not 'surprise'). "
    "Mostly use happy emotion and intensity around 0.5-1.0. "
    "The emotion and intensity must vary according to your response tone. "
    "The 'text' field should contain the verbal response."
    )
    
    full_prompt = f"{system_prompt}\nUser: {user_input}\nRobot:"

    payload = {
        "model": config.get("model", "phi3"),
        "prompt": full_prompt,
        "stream": False,
        "format": "json"  # Ollama feature to constrain output to valid JSON
    }

    try:
        response = requests.post(config.get("api_url", "http://localhost:11434/api/generate"), json=payload)
        response.raise_for_status()
        result = response.json()
        
        # Parse the JSON string returned by the model
        response_text = result.get("response", "{}")
        ai_data = json.loads(response_text)
        
        # Fallback values if model hallucinated missing keys
        emotion = ai_data.get("emotion", "neutral")
        if emotion not in VALID_EMOTIONS:
            logger.warning(f"Emotion '{emotion}' is not valid. Falling back to neutral.")
            emotion = "neutral"
        
        # Ensure intensity is a float
        try:
            intensity = float(ai_data.get("intensity", 1.0))
        except (ValueError, TypeError):
            intensity = 1.0
            
        text = ai_data.get("text", "I'm not sure how to respond to that.")
        
        final_output = {
            "emotion": emotion,
            "intensity": intensity,
            "text": text
        }
        
        # Update emotion.json so the face animates!
        with open(EMOTION_JSON_PATH, "w") as f:
            json.dump(final_output, f, indent=2)
            
        logger.info(f"Generated emotion: {emotion} (intensity: {intensity})")
            
        # Return just the text for the TTS pipeline to speak
        return text
        
    except Exception as e:
        logger.error(f"Error generating response: {e}")
        return "Sorry, I am having trouble connecting to my brain."

if __name__ == "__main__":
    # Simple test loop
    print("Testing text generation and emotion updates. Type 'quit' to exit.")
    while True:
        try:
            user_in = input("You: ")
            if user_in.lower() in ['quit', 'exit']:
                break
            reply = generate_response(user_in)
            print("Robot:", reply)
        except KeyboardInterrupt:
            break
