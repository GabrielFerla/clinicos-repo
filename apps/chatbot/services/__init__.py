"""Camada de serviços do chatbot.

Reúne o que orquestra o turno de conversa — cliente de LLM, embeddings e (a
partir do Bloco 4) o ``ChatService``. Nada aqui importa models: a camada de IA
precisa rodar no CI sem banco e sem rede.
"""
