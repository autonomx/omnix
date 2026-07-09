from pathlib import Path

path = Path("apps/web/src/features/chatbot/CharacterManagementPanel.tsx")
text = path.read_text(encoding="utf-8")
old_memory = '<li key={memory.id}><strong>{memory.category}</strong> · {memory.content}</li>'
new_memory = '<li key={memory.id}><strong>{memory.category}</strong> · <span>{memory.content}</span></li>'
old_candidate = '<li key={candidate.id}><strong>{candidate.proposed_category}</strong> · {candidate.proposed_content}</li>'
new_candidate = '<li key={candidate.id}><strong>{candidate.proposed_category}</strong> · <span>{candidate.proposed_content}</span></li>'
if text.count(old_memory) != 1 or text.count(old_candidate) != 1:
    raise RuntimeError('expected character data list items were not found')
text = text.replace(old_memory, new_memory, 1).replace(old_candidate, new_candidate, 1)
path.write_text(text, encoding="utf-8")
