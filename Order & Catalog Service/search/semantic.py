import logging
import os

from openai import OpenAI

logger = logging.getLogger(__name__)


def get_openai_client():
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        logger.warning("OPENAI_API_KEY is not set.")
        return None
    return OpenAI(api_key=api_key)


def get_embedding(text: str, model="text-embedding-3-small") -> list[float]:
    """
    Generate an embedding vector for a given text using OpenAI.
    """
    client = get_openai_client()
    if not client:
        return []

    text = text.replace("\n", " ")
    try:
        response = client.embeddings.create(input=[text], model=model)
        return response.data[0].embedding
    except Exception as e:
        logger.error(f"Error generating embedding for text '{text[:30]}...': {e}")
        return []


def generate_product_embedding_text(product) -> str:
    """
    Format product information into a rich string for semantic search.
    """
    return f"Product: {product.name}. Description: {product.description}. Category: {product.category.name if product.category else 'None'}."
