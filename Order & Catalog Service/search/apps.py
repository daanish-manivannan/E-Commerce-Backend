from decouple import config
from django.apps import AppConfig
from elasticsearch_dsl import connections


class SearchConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "search"

    def ready(self):
        # Initialize Elasticsearch connection
        es_url = config("ELASTICSEARCH_URL", default="http://elasticsearch:9200")
        connections.create_connection(alias="default", hosts=[es_url])

        # Import signals to register them
        import search.signals  # noqa
