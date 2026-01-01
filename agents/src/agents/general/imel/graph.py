from langchain_ollama import ChatOllama

# Initialize Gemma 3 via Ollama
gemma = ChatOllama(model="gemma3:4b", 
                    temperature=0.5,
)

