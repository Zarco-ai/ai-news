# AI News

A WhatsApp-based AI tutor and news companion powered by OpenAI. Chat with an AI assistant through WhatsApp with support for text messages and voice notes.

## Features

- **WhatsApp Integration**: Seamlessly interact via WhatsApp Cloud API
- **AI Conversations**: Powered by OpenAI's GPT models for intelligent responses
- **Voice Support**: Send and receive voice notes with automatic speech-to-text (STT) and text-to-speech (TTS)
- **Budget Controls**: Built-in spending caps and per-user daily message limits
- **Age Verification**: Optional age confirmation for users
- **Message Deduplication**: Handles webhook retries gracefully
- **Production Ready**: Deployed on Render with PostgreSQL database

## Tech Stack

- **Backend**: Python Flask
- **Database**: PostgreSQL with SQLAlchemy ORM
- **AI Provider**: OpenAI API (GPT models)
- **Messaging**: WhatsApp Cloud API
- **Deployment**: Render (with Gunicorn)
- **Database Migrations**: Alembic

## Getting Started

### Prerequisites

- Python 3.10+
- PostgreSQL database
- WhatsApp Business Account with Meta API access
- OpenAI API key

### Installation

1. Clone the repository
```bash
git clone <repository-url>
cd ai-news
```

2. Create a `.env` file from the example:
```bash
cp .env.example .env
```

3. Update `.env` with your credentials:
```
ACCESS_TOKEN=your_meta_access_token
APP_ID=your_app_id
APP_SECRET=your_app_secret
PHONE_NUMBER_ID=your_phone_number_id
VERIFY_TOKEN=your_webhook_verify_token
OPENAI_API_KEY=your_openai_api_key
DATABASE_URL=postgresql://user:password@localhost:5432/ai_news
```

4. Install dependencies:
```bash
pip install -r requirements.txt
```

5. Initialize the database:
```bash
python -m alembic upgrade head
```

6. Run the application:
```bash
python run.py
```

The app will start on `http://localhost:8000` by default.

## Configuration

### Environment Variables

Key configuration options in `.env`:

- `OPENAI_MODEL`: Model to use for responses (default: `gpt-4o-mini`)
- `VOICE_ENABLED`: Enable/disable voice note processing (default: `true`)
- `STT_MODEL`: Speech-to-text model (default: `gpt-4o-mini-transcribe`)
- `TTS_MODEL`: Text-to-speech model (default: `gpt-4o-mini-tts`)
- `GLOBAL_SPEND_CAP_USD`: Hard spending limit (default: `4.50`)
- `PER_USER_DAILY_LIMIT`: Max messages per user per day (default: `20`)

### Budget Controls

The application implements two levels of spending control:

1. **Global Cap**: Hard limit on total spending across all users
2. **Per-User Daily Limit**: Maximum number of AI-answered messages per user per UTC day

Pricing is calculated based on OpenAI token counts for both input and output.

## Project Structure

```
├── run.py                 # Application entry point
├── requirements.txt       # Python dependencies
├── .env.example          # Environment configuration template
├── app/
│   ├── __init__.py       # Flask app factory
│   ├── config.py         # Configuration management
│   ├── views.py          # Webhook handlers
│   ├── decorators/       # Security decorators
│   ├── db/               # Database models, session, repository
│   ├── services/         # OpenAI and voice services
│   └── utils/            # Utility functions for WhatsApp
├── migrations/           # Database migration scripts (Alembic)
└── scripts/              # Administrative scripts
```

## Deployment

The application is configured for deployment on Render:

1. Connect your GitHub repository to Render
2. Set environment variables in the Render dashboard
3. The application uses Gunicorn as the production server:
   ```bash
   gunicorn "run:app" --bind 0.0.0.0:$PORT
   ```

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Support

For issues or questions, please open an issue on the GitHub repository.
