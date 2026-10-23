description: Create a subagent definition file in .claude/agents
argument-hint: <name> "<description>" "<tools>"
---
name: $0
description: $1
tools: $2
model: opus
---
$3