# Stripe Sankey Widget

An interactive Sankey diagram widget for understanding how samples are represented by topics across different LDA models. This tool can also be applied to similar algorithms like NMF and LSA.

LDA is a powerful tool for achieving soft clustering and finding latent groups beyond initial hypotheses. However, the challenge of applying LDA to 16S rRNA data is that sequence reads are less informative than human language when users want to evaluate a model's results. Even when metrics are applied, making decisions remains difficult.

We designed this StripeSankey diagram to make LDA results more accessible and integrated two widely used metrics—perplexity and coherence score—into novel visual encodings.

Overview of StripeSankey diagram:
<img src="fig/StrpeSankey_metic.jpeg" alt="Description" width="600">

Legend of metrics coour: 
<img src="fig/legend.png" alt="Description" width="600">

After click one flow:
<img src="fig/StrpeSankey_click.jpg" alt="Description" width="600">



## Installation

### From PyPI
```bash
pip install StripeSankey
```
## Data Preprocessing

## Quick Start

```python
import stripe_sankey
from stripe_sankey import StripeSankeyInline

# Load your processed topic modeling data
sankey_data = {
    "nodes": {
        "K2_MC1": {
            "high_count": 45,
            "medium_count": 23,
            "model_metrics": {"perplexity": 1.2},
            "mallet_diagnostics": {"coherence": -0.15}
        },
        # ... more nodes
    },
    "flows": [
        {
            "source_segment": "K2_MC1_high",
            "target_segment": "K3_MC2_medium", 
            "source_k": 2,
            "target_k": 3,
            "sample_count": 15,
            "samples": [{"sample": "doc_1", "source_prob": 0.8, "target_prob": 0.6}]
        },
        # ... more flows
    ],
    "k_range": [2, 3, 4, 5]
}

# Create and display widget
widget = StripeSankeyInline(sankey_data=sankey_data)
widget
```

## Visualization Modes

### Default Mode
Shows topic representations with high/medium probability segments:
```python
widget = StripeSankeyInline(sankey_data=data, mode="default")
```

### Metric Mode  
Color-codes topics by quality metrics (perplexity + coherence):
```python
widget = StripeSankeyInline(sankey_data=data, mode="metric")

# Customize metric weights
widget.update_metric_config(red_weight=0.9, blue_weight=0.7)
```

## Interactive Features

### Sample Flow Tracing
- **Click any flow** to highlight sample trajectories across K values
- **Orange trajectories** show where samples move between topics
- **Count badges** display number of traced samples in each segment
- **Line thickness** represents sample flow volume
- **Click background** to clear selection

### Visual Elements
- **Stacked bars**: High (dark) and medium (light) probability representations
- **Curved flows**: Proportional thickness based on sample counts
- **Barycenter layout**: Optimized positioning to reduce visual complexity
- **Hover tooltips**: Detailed information on flows and segments

## Data Format

Your data should follow this structure:

```python
{
    "nodes": {
        "K{k}_MC{mc}": {
            "high_count": int,           # Samples with prob ≥ 0.67
            "medium_count": int,         # Samples with prob 0.33-0.66
            "total_probability": float,
            "model_metrics": {
                "perplexity": float      # Lower is better
            },
            "mallet_diagnostics": {
                "coherence": float       # Higher (less negative) is better
            }
        }
    },
    "flows": [
        {
            "source_segment": "K{k}_MC{mc}_{level}",
            "target_segment": "K{k+1}_MC{mc}_{level}",
            "source_k": int,
            "target_k": int,
            "sample_count": int,
            "average_probability": float,
            "samples": [
                {
                    "sample": str,           # Sample identifier
                    "source_prob": float,    # Probability in source topic
                    "target_prob": float     # Probability in target topic
                }
            ]
        }
    ],
    "k_range": [2, 3, 4, 5]  # Topic numbers analyzed
}
```

## Configuration Options

### Widget Parameters
```python
widget = StripeSankeyInline(
    sankey_data=data,
    width=1200,           # Canvas width
    height=800,           # Canvas height  
    mode="default"        # "default" or "metric"
)
```

### Metric Mode Configuration
```python
widget.update_metric_config(
    red_weight=0.8,       # Perplexity influence (0-1)
    blue_weight=0.8,      # Coherence influence (0-1) 
    min_saturation=0.3    # Minimum color brightness
)
```

### Color Schemes
```python
widget.color_schemes = {
    2: "#1f77b4",  # Blue for K=2
    3: "#ff7f0e",  # Orange for K=3
    4: "#2ca02c",  # Green for K=4
    5: "#d62728"   # Red for K=5
}
```

## Use Cases

- **Topic Model Analysis**: Understand how topics evolve across different K values
- **Sample Trajectory Tracking**: Follow samples through topic assignments
- **Model Quality Assessment**: Visual comparison of perplexity and coherence metrics
- **Flow Bottleneck Detection**: Identify where samples cluster or disperse
- **Research Presentation**: Interactive demonstrations of topic modeling results


## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

<!-- ## Citation

If you use this widget in your research, please cite:

```bibtex
@software{stripe_sankey,
  title = {Stripe Sankey Widget: Interactive Topic Flow Visualization},
  author = {Your Name},
  url = {https://github.com/Peiyangg/StripeSankey},
  year = {2024}
}
``` -->

## Acknowledgments

- Built with [anywidget](https://anywidget.dev/) - modern Jupyter widget framework
- Visualization powered by [D3.js](https://d3js.org/)

## Support

- 📖 [Documentation](https://github.com/Peiyangg/StripeSankey#readme)