import pytest
from project_generator import CodeExtractor

def test_extract_code_block_with_filename():
    text = """
Here is some code:
```python: app.py
print('hi')
```
"""
    blocks = CodeExtractor.extract_code_blocks(text)
    assert ('python', "print('hi')", 'app.py') in blocks
