import unittest

from sparql.syntax_validator import validate_syntax


class ValidateSyntaxTests(unittest.TestCase):
    def test_valid_query_gives_no_errors(self):
        query = """
PREFIX ceo: <https://linkeddata.cultureelerfgoed.nl/def/ceo#>
SELECT ?rm WHERE {
  ?rm a ceo:Rijksmonument .
}
"""
        self.assertEqual(validate_syntax(query), [])

    def test_unclosed_uri_is_rejected(self):
        query = """
PREFIX ceo: <https://linkeddata.cultureelerfgoed.nl/def/ceo#>
SELECT ?rm WHERE {
  ?rm a ceo:Rijksmonument .
  ?rm ceo:heeftGemeente <http://standaarden.overheid.nl/owms/terms/Utrecht_(gemeente) .
}
"""
        errors = validate_syntax(query)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].startswith("SPARQL-syntaxfout:"))

    def test_missing_where_graph_wrapper_is_rejected(self):
        # talk2thegraph heeft geen postprocess-fix voor dit specifieke geval
        # (chat2thedata wel) -- de syntax-check vangt het generiek op, wat
        # precies de bedoeling is: geen aparte regex nodig per foutpatroon.
        query = """
PREFIX ceo: <https://linkeddata.cultureelerfgoed.nl/def/ceo#>
PREFIX graph: <https://linkeddata.cultureelerfgoed.nl/graph/>
SELECT (COUNT(DISTINCT ?rm) AS ?aantal)
GRAPH graph:instanties-rce {
  ?rm a ceo:Rijksmonument .
}
"""
        self.assertEqual(len(validate_syntax(query)), 1)

    def test_double_comparison_operator_is_rejected(self):
        query = """
PREFIX ceo: <https://linkeddata.cultureelerfgoed.nl/def/ceo#>
PREFIX xsd: <http://www.w3.org/2001/XMLSchema#>
SELECT ?rm ?jaar WHERE {
  ?rm a ceo:Rijksmonument .
  ?rm ceo:registratiedatum ?jaar .
  FILTER(?jaar > > "2000-01-01"^^xsd:date)
}
"""
        self.assertEqual(len(validate_syntax(query)), 1)


if __name__ == "__main__":
    unittest.main()
