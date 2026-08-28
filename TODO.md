# Backlog

Verzameling van uitgestelde ideeën en openstaande verificaties, besproken
maar bewust nog niet opgepakt. Geen vaste volgorde binnen een sectie tenzij
anders aangegeven.

## Betrouwbaarheid / verificatie (eerst doen voordat je hierop vertrouwt)

- **Nooit getest met een echte LLM-aanroep.** Alle fixes rond SPARQL-generatie
  (gemeente-resolutie, completeness-check) zijn alleen getest met een
  gemockte `_generate()`. Niet geverifieerd of de daadwerkelijk
  geconfigureerde provider (Ollama/Anthropic/Google) zich in de praktijk aan
  de nieuwe regels houdt.
- **De TopologyException-fallback (`sparql/spatial.py`) is nooit tegen een
  echte fout getest**, alleen tegen een gemockte HTTPError. Zoek een
  reproduceerbaar geval op het live endpoint en verifieer de fallback
  daadwerkelijk aanslaat.
- **Geen live Render-deploy geverifieerd.** De README-instructies voor
  Render, environment variables en `gunicorn app:app` zijn nooit in de
  praktijk getest.
- **Geen JS-testrunner.** De WKT/GeoJSON-parsing (`parseWktToLayers`,
  `parseWktToGeoJSON`, `stripOuterParens`, ...) is alleen handmatig via de
  browserconsole getest, niet met een geautomatiseerde test. Toen dat wél
  gebeurde kwam er meteen een echte bug uit (MultiPolygon met één ring werd
  fout geparsed) — dus dit is de moeite waard om te automatiseren.

## Monitoring en meldingen

- Geen alerting bij herhaaldelijk geraakte rate limits, LLM-providerfouten,
  of vaak aanslaande ruimtelijke fallback — nu alleen zichtbaar in de
  Render-logs als je er zelf naar kijkt.
- Geen error tracking (bv. Sentry) voor onverwachte 500's in productie.
- Geen CI: de testsuite draait alleen lokaal/handmatig, niet automatisch bij
  een push (bv. GitHub Actions).

## Features — kleinere/middelgrote moeite

- Cache voor veelgestelde vragen (bespaart LLM-kosten en latency —
  waarschijnlijk de hoogste ROI van de resterende lijst).
- Keuze tussen snel/goedkoop/nauwkeurig model (meerdere modelpresets per
  provider, front- en backend).
- Knoppen voor goed/fout antwoord — moet ergens opgeslagen worden (bestand?
  database? alleen loggen?), nog te bepalen.
- Kaartlagen voor monumenten en gezichten los aan/uit te zetten.

## Features — grotere investering

- Markerclustering bij grote resultaten (vereist een externe
  Leaflet-plugin, moet gevendord worden net als de rest van Leaflet).
- Querybibliotheek met betrouwbare sjablonen (sla bewezen queries op i.p.v.
  steeds opnieuw te laten genereren) — apart project.
- Verdergaande automatische tweede controle van gegenereerde SPARQL. Bestaat
  al deels via `validate_semantics`/`validate_completeness`
  (regelgebaseerd, gratis); een extra LLM-kritiekronde kost een extra
  aanroep per vraag — pas doen als de regelgebaseerde aanpak in de praktijk
  tekortschiet.

## Beveiliging (doorlopend, geen eenmalige actie)

- Cloudflare Turnstile voor de publieke deploy (genoemd, nog niet opgepakt).
- Gedeelde rate-limit-store (bv. Redis) zodra er meer dan één
  gunicorn-worker of Render-instance draait — nu in-memory, dus niet gedeeld.
- Periodiek nalopen of `APP_ACCESS_CODE` en de rate limits nog passen bij
  het daadwerkelijke gebruik zodra de app publiek staat.
