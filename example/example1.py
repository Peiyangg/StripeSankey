import marimo

__generated_with = "0.11.8"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as mo
    import pandas as pd
    import random
    import numpy as np
    from StripeSankey import StripeSankeyInline
    from scipy.stats import dirichlet
    return StripeSankeyInline, dirichlet, mo, np, pd, random


@app.cell(hide_code=True)
def _(dirichlet, np, random):
    def create_lda_demo_data(alpha=0.5, num_documents=150, seed=42):
        """
        Creates realistic LDA demo data using Dirichlet distributions
    
        Parameters:
        - alpha: Dirichlet concentration parameter (0.5 creates sparse distributions)
        - num_documents: Number of documents to simulate
        - seed: Random seed for reproducibility
        """
    
        # Set seeds for reproducibility
        np.random.seed(seed)
        random.seed(seed)
    
        k_values = [2, 3, 4, 5]
        document_names = [f"doc_{i:03d}" for i in range(1, num_documents + 1)]
    
        demo_data = {
            "k_range": k_values,
            "nodes": {},
            "flows": []
        }
    
        # Store document-topic distributions for each K
        doc_topic_distributions = {}
    
        # Generate LDA results for each K value
        for k in k_values:
            print(f"Generating LDA results for K={k}...")
        
            # Generate document-topic distributions using Dirichlet(alpha)
            # Lower alpha (0.5) creates sparser, more peaked distributions
            alpha_vec = np.full(k, alpha)
            doc_topic_dist = dirichlet.rvs(alpha_vec, size=num_documents)
            doc_topic_distributions[k] = doc_topic_dist
        
            # Create nodes (topics) for this K value
            for mc in range(1, k + 1):
                node_id = f"K{k}_MC{mc}"
            
                # Get topic probabilities for all documents for this topic (0-indexed)
                topic_probs = doc_topic_dist[:, mc - 1]
            
                # Classify documents by probability thresholds
                high_mask = topic_probs >= 0.67
                medium_mask = (topic_probs >= 0.33) & (topic_probs < 0.67)
            
                high_docs = [doc for i, doc in enumerate(document_names) if high_mask[i]]
                medium_docs = [doc for i, doc in enumerate(document_names) if medium_mask[i]]
            
                high_count = len(high_docs)
                medium_count = len(medium_docs)
            
                # Calculate total probability mass for this topic
                total_prob = np.sum(topic_probs)
            
                # Generate realistic quality metrics based on topic coherence
                # More coherent topics (higher doc concentration) have better metrics
                topic_concentration = np.std(topic_probs)  # Higher std = more concentrated
            
                # Perplexity: lower is better, influenced by topic concentration
                base_perplexity = 2.5
                perplexity = base_perplexity - (topic_concentration * 1.2) + np.random.normal(0, 0.1)
                perplexity = max(1.1, perplexity)  # Ensure reasonable bounds
            
                # Coherence: higher (less negative) is better
                base_coherence = -0.8
                coherence = base_coherence + (topic_concentration * 0.8) + np.random.normal(0, 0.05)
                coherence = min(-0.1, coherence)  # Ensure reasonable bounds
            
                demo_data["nodes"][node_id] = {
                    "high_count": high_count,
                    "medium_count": medium_count,
                    "total_probability": float(total_prob),
                    "high_samples": high_docs,
                    "medium_samples": medium_docs,
                    "model_metrics": {
                        "perplexity": round(perplexity, 3)
                    },
                    "mallet_diagnostics": {
                        "coherence": round(coherence, 3)
                    }
                }
    
        # Generate flows between adjacent K values based on document assignments
        print("Generating topic flows between K values...")
    
        for i in range(len(k_values) - 1):
            source_k = k_values[i]
            target_k = k_values[i + 1]
        
            source_dist = doc_topic_distributions[source_k]
            target_dist = doc_topic_distributions[target_k]
        
            # For each document, find its primary topic assignments in both K values
            source_assignments = np.argmax(source_dist, axis=1)  # Primary topic for each doc
            target_assignments = np.argmax(target_dist, axis=1)
        
            # Create flow tracking
            flows_dict = {}
        
            for doc_idx, doc_name in enumerate(document_names):
                source_topic_idx = source_assignments[doc_idx]
                target_topic_idx = target_assignments[doc_idx]
            
                source_prob = source_dist[doc_idx, source_topic_idx]
                target_prob = target_dist[doc_idx, target_topic_idx]
            
                # Determine probability levels
                source_level = 'high' if source_prob >= 0.67 else ('medium' if source_prob >= 0.33 else 'low')
                target_level = 'high' if target_prob >= 0.67 else ('medium' if target_prob >= 0.33 else 'low')
            
                # Only track medium and high probability assignments
                if source_level in ['high', 'medium'] and target_level in ['high', 'medium']:
                    source_topic_name = f"K{source_k}_MC{source_topic_idx + 1}"
                    target_topic_name = f"K{target_k}_MC{target_topic_idx + 1}"
                
                    flow_key = (
                        f"{source_topic_name}_{source_level}",
                        f"{target_topic_name}_{target_level}",
                        source_k,
                        target_k
                    )
                
                    if flow_key not in flows_dict:
                        flows_dict[flow_key] = []
                
                    flows_dict[flow_key].append({
                        "sample": doc_name,
                        "source_prob": float(source_prob),
                        "target_prob": float(target_prob)
                    })
        
            # Convert flows to required format
            for (source_seg, target_seg, sk, tk), samples in flows_dict.items():
                if len(samples) >= 10:  # Only include significant flows
                    flow = {
                        "source_segment": source_seg,
                        "target_segment": target_seg,
                        "source_k": sk,
                        "target_k": tk,
                        "sample_count": len(samples),
                        "average_probability": np.mean([s["source_prob"] + s["target_prob"] for s in samples]) / 2,
                        "samples": samples
                    }
                    demo_data["flows"].append(flow)
    
        return demo_data
    return (create_lda_demo_data,)


@app.cell
def _(create_lda_demo_data):
    lda_demo_data = create_lda_demo_data(alpha=0.5, num_documents=1200, seed=42)
    sankey_demo_data = lda_demo_data
    return lda_demo_data, sankey_demo_data


@app.cell
def _(StripeSankeyInline, sankey_demo_data):
    widget = StripeSankeyInline(sankey_data=sankey_demo_data)
    return (widget,)


@app.cell
def _(widget):
    widget
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
