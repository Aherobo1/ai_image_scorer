# ai_image_scorer

ai_image_scorer is a FastAPI-based AI image scoring and enhancement app for social media content. It scores uploaded images across four pillars, can generate improved versions, and rescales the results for comparison.

## What it does

- Scores images with a 4-part rubric: definition, layout, mood, and vibe check.
- Accepts optional preferences such as aesthetic, niche, target audience, content type, and brand voice.
- Generates enhanced versions with Gemini 2.5 Flash.
- Falls back to OpenAI if Gemini is unavailable.
- Serves a web frontend from the same FastAPI app.
- Uses Google Cloud Vision SafeSearch for moderation.

## Requirements

- Python 3.11 or newer
- A Gemini API key: `GEMINI_API_KEY`
- Optional OpenAI fallback key: `OPENAI_API_KEY`
- Google Cloud credentials for moderation: `GOOGLE_APPLICATION_CREDENTIALS`

## Setup

1. Create and activate a virtual environment.

```bash
python -m venv venv
source venv/bin/activate
```

2. Install dependencies.

```bash
pip install -r requirements.txt
```

3. Create your environment file.

```bash
cp .env.example .env
```

4. Fill in `.env` with your keys.

```bash
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
GOOGLE_APPLICATION_CREDENTIALS=/path/to/google-credentials.json
```

## Run

Start the app from the project root:

```bash
python api.py
```

On macOS/Linux, you can also use:

```bash
./start_server.sh
```

Open the app at:

- `http://localhost:5300`
- `http://localhost:5300/health`

## API Endpoints

- `GET /` serves the frontend when `frontend/index.html` exists
- `POST /test-post` simple POST test endpoint
- `POST /score-image` score one base64-encoded image
- `POST /score-images` score multiple images in parallel
- `POST /enhance-image` generate enhanced versions of an image
- `POST /custom-prompt` enhance an image using a custom instruction
- `GET /health` server and scorer health check
- `GET /scoring-weights` current pillar weights
- `GET /available-preferences` supported preference options
- `GET /moderation-status` SafeSearch moderation status

## Request Example

```json
{
  "image": "base64-encoded-image-data",
  "user_preferences": {
    "aesthetic": "Minimalist",
    "niche": "Fashion Influencer",
    "target_audience": "Gen Z",
    "content_type": "Instagram Post",
    "brand_voice": "Playful and Trendy"
  }
}
```

The enhancement endpoints accept `num_versions` from 1 to 5, and `/custom-prompt` also requires a `custom_prompt` string.

## Key Files

- [api.py](api.py) FastAPI app and endpoints
- [viral_velocity_scorer.py](viral_velocity_scorer.py) scoring logic
- [image_enhancer.py](image_enhancer.py) image enhancement pipeline
- [content_moderator.py](content_moderator.py) SafeSearch wrapper
- [frontend/index.html](frontend/index.html) web UI
- [frontend/script.js](frontend/script.js) frontend behavior
- [.env.example](.env.example) sample environment variables

## Notes

- Images are written to temporary files during processing and cleaned up afterward.
- The app supports JPEG, PNG, WebP, and HEIC/HEIF when the environment has the right libraries installed.
- There is no separate frontend build step; the backend serves the UI directly.

## GitHub Repo

If you are creating the repository on GitHub, use:

```bash
https://github.com/Aherobo1/ai_image_scorer.git
```

To publish from this folder:

```bash
git remote add origin https://github.com/Aherobo1/ai_image_scorer.git
git add README.md .env.example .gitignore api.py frontend/index.html frontend/script.js
git commit -m "docs: rename project to ai_image_scorer"
git push -u origin main
```
