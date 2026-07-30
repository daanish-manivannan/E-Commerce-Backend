from elasticsearch_dsl import Boolean, Document, Float, Integer, Keyword, Text


class ProductDocument(Document):
    id = Integer()
    name = Text(fields={"keyword": Keyword()})
    description = Text()
    price = Float()
    category = Keyword()
    is_active = Boolean()

    class Index:
        name = "products"
        settings = {"number_of_shards": 1, "number_of_replicas": 0}
