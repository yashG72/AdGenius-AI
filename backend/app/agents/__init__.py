"""Multi-agent campaign workflow (LangGraph).

Six agent roles collaborate through a typed shared state and deterministic edges:
Campaign Manager -> (Brand Research || Competitor Intelligence) -> Creative Strategist
-> human concept approval -> Scriptwriter -> Visual Director -> Critic (-> revisions).
"""
