# Wikipedia Neural Network in PyTorch

This script implements a 3-layer feedforward neural network (Input Layer, Hidden Layer, Output Layer) using PyTorch, modeled after the standard Wikipedia neural network diagram.

## Code (`workers/workspace_worker/scripts/wikipedia_neural_network.py`)

```python
import torch
import torch.nn as nn

class WikipediaNeuralNetwork(nn.Module):
    \"\"\"
    A 3-layer feedforward neural network (Input, Hidden, Output)
    modeled after the canonical neural network diagram on Wikipedia.
    \"\"\"
    def __init__(self, input_size=3, hidden_size=4, output_size=2):
        super(WikipediaNeuralNetwork, self).__init__()
        self.hidden = nn.Linear(input_size, hidden_size)
        self.sigmoid = nn.Sigmoid()
        self.output = nn.Linear(hidden_size, output_size)

    def forward(self, x):
        x = self.hidden(x)
        x = self.sigmoid(x)
        x = self.output(x)
        return x

if __name__ == "__main__":
    model = WikipediaNeuralNetwork(input_size=3, hidden_size=4, output_size=2)
    print("--- Wikipedia Neural Network Structure ---")
    print(model)
    
    # Test forward pass with dummy batch of 2 samples, 3 features each
    sample_input = torch.tensor([[0.5, -0.2, 0.1], [1.0, 0.0, -1.0]])
    prediction = model(sample_input)
    print("\\n--- Test Forward Pass ---")
    print(f"Input shape: {sample_input.shape}")
    print(f"Output shape: {prediction.shape}")
    print(f"Outputs:\\n{prediction}")
```

## How to Run
```bash
pip install torch
python workers/workspace_worker/scripts/wikipedia_neural_network.py
```
