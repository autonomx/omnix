def process(intent):
    # Simulate pipeline processing
    # In real implementation, this would call the full simulation pipeline
    return type('Result', (), {
        'success': True,
        'description': f"Processed action: {intent['action']}",
        'effects': [],
        'roll': None,
        'damage': None,
        'target': intent.get('target', None)
    })()