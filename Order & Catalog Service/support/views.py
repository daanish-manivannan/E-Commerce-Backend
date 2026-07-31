import os

from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView


class SupportChatView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        message = request.data.get("message")
        if not message:
            return Response({"error": "Message is required"}, status=400)

        api_key = os.environ.get("OPENAI_API_KEY")
        if not api_key:
            return Response({"error": "AI support is not configured"}, status=500)

        # Basic RAG or direct LLM integration
        # For this milestone, we'll just use a basic ChatOpenAI instance to answer questions
        try:
            llm = ChatOpenAI(model="gpt-4o-mini", api_key=api_key, temperature=0.2)

            prompt = PromptTemplate(
                input_variables=["question"],
                template="You are a helpful customer support assistant for our E-commerce platform. Answer the following question from a user:\n\nUser: {question}\nAssistant:",
            )

            chain = prompt | llm

            response = chain.invoke({"question": message})

            return Response({"response": response.content})
        except Exception as e:
            return Response({"error": str(e)}, status=500)
