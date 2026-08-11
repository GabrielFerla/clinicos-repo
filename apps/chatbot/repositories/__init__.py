"""Repositórios do chatbot — queries que não cabem no ORM.

Padrão definido em ``docs/ARQUITETURA.md``: quando a query envolve SQL bruto
(caso da busca vetorial), ela mora num repositório em vez de vazar para o
service ou para a view.
"""
