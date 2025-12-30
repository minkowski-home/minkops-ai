from typing import Annotated, TypedDict, Literal
from langgraph.graph import StateGraph, START, END  # type: ignore
from langchain_ollama import ChatOllama
from langgraph.types import Command
from langchain_core.messages import HumanMessage
import os
import dotenv

dotenv.load_dotenv()



# Initialize Gemma 3 via Ollama
gemma = ChatOllama(model="gemma3:4b", 
                    temperature=0.5,
)

