# Presidio analyzer with a German spaCy model.
# Build-time only: the model is downloaded here (needs internet on the host
# build), so the running container stays read-only and egress-less.
#
# de_core_news_lg (~550 MB) over _sm: PERSON/LOCATION come from NER only, and the
# small model's NER is the weak point (the "einem Satz" -> PERSON false positive
# came from the wrong-language model, but sm would trade it for missed names).
FROM ghcr.io/data-privacy-stack/presidio-analyzer:latest

USER root
RUN python -m spacy download de_core_news_lg \
    && python -m spacy validate
COPY nlp_de_en.yaml analyzer_de_en.yaml recognizers_de_en.yaml /app/conf-de/
RUN chmod -R a+rX /app/conf-de
USER 1001

ENV NLP_CONF_FILE=/app/conf-de/nlp_de_en.yaml \
    ANALYZER_CONF_FILE=/app/conf-de/analyzer_de_en.yaml \
    RECOGNIZER_REGISTRY_CONF_FILE=/app/conf-de/recognizers_de_en.yaml
