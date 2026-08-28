import os
import unittest
from unittest.mock import patch

os.environ.setdefault("LLM_PROVIDER", "ollama")

import config
from answer import answer_generator
from sparql.executor import _validate_read_query
from sparql.postprocess import inject_prefixes


class QueryValidationTests(unittest.TestCase):
    def test_select_with_geo_prefix_is_allowed(self):
        _validate_read_query(
            "PREFIX geo: <http://www.opengis.net/ont/geosparql#>\n"
            "SELECT * WHERE { ?s geo:hasGeometry ?g }"
        )

    def test_update_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "SELECT- en ASK"):
            _validate_read_query("DELETE WHERE { ?s ?p ?o }")

    def test_missing_geo_prefix_is_injected(self):
        query = inject_prefixes(
            "SELECT * WHERE { ?s geo:hasGeometry ?g . ?g geo:asWKT ?wkt }"
        )
        self.assertIn(
            "PREFIX geo: <http://www.opengis.net/ont/geosparql#>", query
        )


class AnswerTests(unittest.TestCase):
    def test_count_uses_sparql_value(self):
        results = {
            "head": {"vars": ["aantal"]},
            "results": {"bindings": [
                {"aantal": {"type": "literal", "value": "6331"}}
            ]},
        }
        self.assertIn("6331", answer_generator.generate("Hoeveel?", results))


class ApiTests(unittest.TestCase):
    def setUp(self):
        from app import app
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_invalid_json_returns_400(self):
        response = self.client.post(
            "/api/generate-sparql", data="geen json", content_type="text/plain"
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.get_json()["error"], "Verwacht een JSON-object")

    def test_root_serves_map_frontend(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("/vendor/leaflet/leaflet.js", html)
        self.assertIn("resultMap", html)
        response.close()

    def test_ollama_needs_no_api_key(self):
        with patch.object(config, "LLM_PROVIDER", "ollama"):
            response = self.client.get("/api/health")
        self.assertTrue(response.get_json()["api_key_set"])


if __name__ == "__main__":
    unittest.main()