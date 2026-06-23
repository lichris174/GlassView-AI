# Golden fixtures

Drop screenshot PNGs here and reference them from `../cases.json` to add
image-grounded eval cases (the harness loads the file and sends it to the model
alongside the question):

```json
{
  "id": "vscode-error-squiggle",
  "question": "What is the error shown in the editor?",
  "image": "fixtures/vscode-error-squiggle.png",
  "contains_any": ["undefined", "is not defined", "cannot find"]
}
```

Keep fixtures small and free of personal data. Text-only cases (no `image`)
exercise reasoning without a screenshot and run anywhere.
