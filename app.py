"""
RCE Erfgoed Assistent — Flask applicatie

Start:
    pip install -r requirements.txt
    cp .env.example .env
    python app.py
"""

import logging
import os

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

import config
from answer import answer_generator
from sparql import executor as sparql_executor
from sparql import sparql_generator


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    datefmt="%H:%M:%S",
)

logger = logging.getLogger(__name__)


def current_model_name() -> str:
    """Geef de actieve modelnaam terug op basis van LLM_PROVIDER."""

    provider = config.LLM_PROVIDER.lower()

    if provider == "ollama":
        return config.OLLAMA_MODEL

    if provider == "google":
        return config.GOOGLE_MODEL

    if provider == "anthropic":
        return config.ANTHROPIC_MODEL

    return "onbekend"


def api_key_available() -> bool:
    """Controleer of de gekozen provider een API key nodig heeft en heeft."""

    provider = config.LLM_PROVIDER.lower()

    if provider == "ollama":
        return True

    if provider == "google":
        return bool(config.GOOGLE_API_KEY)

    if provider == "anthropic":
        return bool(config.ANTHROPIC_API_KEY)

    return False


app = Flask(
    __name__,
    static_folder=os.path.join(os.path.dirname(__file__), "frontend"),
    static_url_path="",
)

CORS(app)


def _json_object():
    """Lees een JSON-object of geef een duidelijke 400-respons."""
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return None, (jsonify({"error": "Verwacht een JSON-object"}), 400)
    return data, None


@app.route("/")
def index():
    """Serveer de frontend."""
    return app.send_static_file("index.html")


@app.route("/api/health", methods=["GET"])
def health():
    """Health check voor backend, provider, model en endpoint."""

    return jsonify(
        {
            "status": "ok",
            "provider": config.LLM_PROVIDER,
            "api_key_set": api_key_available(),
            "model": current_model_name(),
            "endpoint": config.SPARQL_ENDPOINT,
        }
    )

def detect_mode(question: str) -> str:
    q = question.lower()

    telling_triggers = [
        "hoeveel",
        "aantal",
        "tel ",
        "telling",
        "how many",
        "count",
    ]

    if any(x in q for x in telling_triggers):
        return "telling"

    return "lijst"


@app.route("/api/generate-sparql", methods=["POST"])
def generate_sparql():
    """Stap 1: vertaal natuurlijke vraag naar SPARQL."""

    data, error = _json_object()
    if error:
        return error
    question = str(data.get("question") or "").strip()
    frontend_mode = data.get("mode")

    detected_mode = detect_mode(question)

    if detected_mode == "telling":
        mode = "telling"
    else:
        mode = frontend_mode or "lijst"

    if not mode:
        mode = detect_mode(question)

    if not question:
        return jsonify({"error": "Geen vraag opgegeven"}), 400

    if mode not in ("lijst", "telling"):
        return jsonify({"error": "Ongeldige modus. Gebruik 'lijst' of 'telling'."}), 400

    try:
        query = sparql_generator.generate(question, mode)
        return jsonify({"query": query})

    except Exception as e:
        logger.exception("Fout bij SPARQL generatie")
        return jsonify({"error": str(e)}), 500


@app.route("/api/execute-sparql", methods=["POST"])
def execute_sparql():
    """Stap 2: voer SPARQL query uit op het RCE endpoint."""

    data, error = _json_object()
    if error:
        return error
    query = str(data.get("query") or "").strip()

    if not query:
        return jsonify({"error": "Geen query opgegeven"}), 400

    try:
        results = sparql_executor.execute(query)
        return jsonify(results)

    except ValueError as exc:
        return jsonify({"error": str(exc)}), 400

    except requests.exceptions.Timeout:
        return jsonify({"error": "Endpoint timeout (>30s)"}), 504

    except requests.exceptions.HTTPError as e:
        return (
            jsonify(
                {
                    "error": (
                        f"Endpoint fout: {e.response.status_code} — "
                        f"{e.response.text[:300]}"
                    )
                }
            ),
            502,
        )

    except Exception as e:
        logger.exception("Fout bij SPARQL uitvoering")
        return jsonify({"error": str(e)}), 500


@app.route("/api/generate-answer", methods=["POST"])
def generate_answer():
    """Stap 3: vertaal SPARQL resultaten naar leesbaar antwoord."""

    data, error = _json_object()
    if error:
        return error
    question = str(data.get("question") or "").strip()
    results = data.get("results", {})
    if not isinstance(results, dict):
        return jsonify({"error": "'results' moet een JSON-object zijn"}), 400

    try:
        answer = answer_generator.generate(question, results)
        return jsonify({"answer": answer})

    except Exception as e:
        logger.exception("Fout bij antwoord generatie")
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    port = int(os.environ.get("PORT", config.FLASK_PORT))

    logger.info("SPARQL endpoint: %s", config.SPARQL_ENDPOINT)
    logger.info("Provider: %s", config.LLM_PROVIDER)
    logger.info("Model: %s", current_model_name())
    logger.info("Server start op poort %d", port)

    app.run(
        host="0.0.0.0",
        debug=config.FLASK_DEBUG,
        port=port,
    )