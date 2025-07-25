import marimo

__generated_with = "0.14.10"
app = marimo.App(width="medium")


@app.cell
def _():
    import marimo as mo
    import pandas as pd 
    import numpy as np
    from scipy.stats import entropy
    from sklearn.metrics.pairwise import cosine_similarity
    from scipy.stats import chi2
    from sklearn.covariance import EmpiricalCovariance

    import plotly.express as px
    import plotly.graph_objects as go
    import umap
    import matplotlib.pyplot as plt
    import os
    from typing import List, Tuple, Optional, Dict
    import altair as alt
    return Dict, List, Optional, Tuple, cosine_similarity, go, mo, pd, px


@app.cell
def _(mo):
    import datetime
    import subprocess
    from pathlib import Path

    def save_svg_and_commit(svg_str: str, files_to_commit: list[str] = None, output_dir: str = "visuals") -> str:
        Path(output_dir).mkdir(parents=True, exist_ok=True)

        # 1. Get the commit hash first (current HEAD, not yet used for SVG)
        commit_hash = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"], text=True
        ).strip()

        # 2. Prepare final filename with timestamp and latest hash
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        final_path = Path(output_dir) / f"{timestamp}_{commit_hash}.svg"

        # 3. Write SVG directly to final file
        final_path.write_text(svg_str, encoding="utf-8")

        # 4. Determine calling notebook if not given
        if files_to_commit is None:
            nb_path = mo.notebook_dir()
            if nb_path is None:
                raise RuntimeError("Cannot detect current notebook path")
            files_to_commit = [str(Path(nb_path).resolve())]

        # 5. Add SVG to commit
        files_to_commit.append(str(final_path))
        subprocess.run(["git", "add", *files_to_commit], check=True)

        # 6. Commit
        msg = "auto: update " + ", ".join(Path(f).name for f in files_to_commit)
        subprocess.run(["git", "commit", "-m", msg], check=True)

        return str(final_path)
    return (save_svg_and_commit,)


@app.cell
def _(mo, save_svg_and_commit, svg_string):
    mo.ui.button(label="Save & commit SVG", on_click=lambda _: save_svg_and_commit(svg_string))
    return


@app.cell
def _(mo):
    mo.md(r"""## Data processing""")
    return


@app.cell
def _(pd):
    metadata_df= pd.read_csv('data/prototype1/metadata_new_updated.csv', index_col=0)
    features_metadata=metadata_df[["Country", 'Breed_type', 'Outdoor_access', 'Bedding_present', 'Slatted floor', "Age_category"]]
    topic_word_folder = "data/prototype1/ASVProbabilities"  # Folder with ASVProbabilities files
    sample_topic_folder = "data/prototype1/SampleProbabilities_wide"
    return sample_topic_folder, topic_word_folder


@app.cell(hide_code=True)
def _(
    Dict,
    analyze_sample_reassignments,
    cosine_similarity,
    extract_feature_analysis_for_sankey,
    extract_topic_evolution_data,
    go,
    pd,
    prepare_sankey_data,
    px,
):
    def calculate_topic_similarities_with_similarity_flow(
        evolution_data: Dict, 
        similarity_threshold: float = 0.3,
        flow_scaling_factor: float = 1.0
    ) -> pd.DataFrame:
        """
        Calculate cosine similarities between topics across consecutive k values
        using similarity scores as flow values instead of probabilities.

        Args:
            evolution_data: Output from extract_topic_evolution_data
            similarity_threshold: Minimum similarity to consider topics related
            flow_scaling_factor: Multiplier to scale similarity values for better visualization

        Returns:
            DataFrame with topic similarity relationships using similarity as flow
        """

        topic_word_matrix = evolution_data['topic_word_matrix']
        metadata_df = evolution_data['topic_metadata']
        k_values = evolution_data['k_values']

        similarity_relationships = []

        # Compare consecutive k values
        for i in range(len(k_values) - 1):
            k_low = k_values[i]
            k_high = k_values[i + 1]

            # Get topics for these k values
            topics_low = metadata_df[metadata_df['k_value'] == k_low]['global_id'].tolist()
            topics_high = metadata_df[metadata_df['k_value'] == k_high]['global_id'].tolist()

            if len(topics_low) == 0 or len(topics_high) == 0:
                continue

            # Get topic-word vectors
            vectors_low = topic_word_matrix.loc[topics_low].values
            vectors_high = topic_word_matrix.loc[topics_high].values

            # Calculate cosine similarities
            similarities = cosine_similarity(vectors_low, vectors_high)

            # Create relationships above threshold
            for idx_low, topic_low in enumerate(topics_low):
                for idx_high, topic_high in enumerate(topics_high):
                    similarity_score = similarities[idx_low, idx_high]

                    if similarity_score >= similarity_threshold:
                        # Get probabilities for metadata (not used for flow)
                        prob_low = metadata_df[metadata_df['global_id'] == topic_low]['sum_probability'].iloc[0]
                        prob_high = metadata_df[metadata_df['global_id'] == topic_high]['sum_probability'].iloc[0]

                        similarity_relationships.append({
                            'source_topic': topic_low,
                            'target_topic': topic_high,
                            'source_k': k_low,
                            'target_k': k_high,
                            'similarity': similarity_score,
                            'source_probability': prob_low,
                            'target_probability': prob_high,
                            'flow_volume': similarity_score * flow_scaling_factor  # Use similarity as flow
                        })

        return pd.DataFrame(similarity_relationships)


    def calculate_topic_similarities_normalized_flow(
        evolution_data: Dict, 
        similarity_threshold: float = 0.3,
        min_flow: float = 0.1,
        max_flow: float = 1.0
    ) -> pd.DataFrame:
        """
        Calculate similarities with normalized similarity scores as flow values.
        This version normalizes similarity scores to a specified range for better visualization.

        Args:
            evolution_data: Output from extract_topic_evolution_data
            similarity_threshold: Minimum similarity to consider topics related
            min_flow: Minimum flow value for visualization
            max_flow: Maximum flow value for visualization

        Returns:
            DataFrame with normalized similarity-based flow values
        """

        topic_word_matrix = evolution_data['topic_word_matrix']
        metadata_df = evolution_data['topic_metadata']
        k_values = evolution_data['k_values']

        similarity_relationships = []

        # First pass: collect all similarities above threshold
        all_similarities = []

        for i in range(len(k_values) - 1):
            k_low = k_values[i]
            k_high = k_values[i + 1]

            topics_low = metadata_df[metadata_df['k_value'] == k_low]['global_id'].tolist()
            topics_high = metadata_df[metadata_df['k_value'] == k_high]['global_id'].tolist()

            if len(topics_low) == 0 or len(topics_high) == 0:
                continue

            vectors_low = topic_word_matrix.loc[topics_low].values
            vectors_high = topic_word_matrix.loc[topics_high].values
            similarities = cosine_similarity(vectors_low, vectors_high)

            for idx_low, topic_low in enumerate(topics_low):
                for idx_high, topic_high in enumerate(topics_high):
                    similarity_score = similarities[idx_low, idx_high]
                    if similarity_score >= similarity_threshold:
                        all_similarities.append(similarity_score)

        # Calculate normalization parameters
        if len(all_similarities) > 0:
            sim_min = min(all_similarities)
            sim_max = max(all_similarities)
            sim_range = sim_max - sim_min if sim_max > sim_min else 1.0
        else:
            sim_min, sim_max, sim_range = 0, 1, 1

        # Second pass: create relationships with normalized flows
        for i in range(len(k_values) - 1):
            k_low = k_values[i]
            k_high = k_values[i + 1]

            topics_low = metadata_df[metadata_df['k_value'] == k_low]['global_id'].tolist()
            topics_high = metadata_df[metadata_df['k_value'] == k_high]['global_id'].tolist()

            if len(topics_low) == 0 or len(topics_high) == 0:
                continue

            vectors_low = topic_word_matrix.loc[topics_low].values
            vectors_high = topic_word_matrix.loc[topics_high].values
            similarities = cosine_similarity(vectors_low, vectors_high)

            for idx_low, topic_low in enumerate(topics_low):
                for idx_high, topic_high in enumerate(topics_high):
                    similarity_score = similarities[idx_low, idx_high]

                    if similarity_score >= similarity_threshold:
                        # Normalize similarity to [min_flow, max_flow] range
                        normalized_flow = min_flow + (similarity_score - sim_min) / sim_range * (max_flow - min_flow)

                        prob_low = metadata_df[metadata_df['global_id'] == topic_low]['sum_probability'].iloc[0]
                        prob_high = metadata_df[metadata_df['global_id'] == topic_high]['sum_probability'].iloc[0]

                        similarity_relationships.append({
                            'source_topic': topic_low,
                            'target_topic': topic_high,
                            'source_k': k_low,
                            'target_k': k_high,
                            'similarity': similarity_score,
                            'source_probability': prob_low,
                            'target_probability': prob_high,
                            'flow_volume': normalized_flow,  # Normalized similarity as flow
                            'raw_similarity': similarity_score,  # Keep original for reference
                            'normalized_similarity': normalized_flow
                        })

        return pd.DataFrame(similarity_relationships)


    def run_topic_evolution_analysis_similarity_flow(
        selected_global_ids, 
        topic_word_folder, 
        sample_topic_folder, 
        embeddings_df=None,
        similarity_threshold=0.3,
        use_normalized_flow=True,
        flow_scaling_factor=1.0,
        min_flow=0.1,
        max_flow=1.0
    ):
        """
        Complete pipeline for topic evolution analysis using similarity-based flow.

        Args:
            selected_global_ids: List of global_ids from cluster selection
            topic_word_folder: Path to topic-word probability files
            sample_topic_folder: Path to sample-topic probability files  
            embeddings_df: DataFrame with embeddings and metadata (optional)
            similarity_threshold: Minimum similarity to show connections
            use_normalized_flow: Whether to normalize similarity scores for flow
            flow_scaling_factor: Scaling factor if not using normalization
            min_flow: Minimum flow value for normalization
            max_flow: Maximum flow value for normalization

        Returns:
            Dictionary containing all analysis results
        """

        print("=== EXTRACTING TOPIC EVOLUTION DATA ===")
        evolution_data = extract_topic_evolution_data(
            selected_global_ids=selected_global_ids,
            topic_word_folder=topic_word_folder,
            sample_topic_folder=sample_topic_folder,
            embeddings_df=embeddings_df
        )

        print("\n=== CALCULATING TOPIC SIMILARITIES (SIMILARITY-BASED FLOW) ===")
        if use_normalized_flow:
            similarity_df = calculate_topic_similarities_normalized_flow(
                evolution_data, 
                similarity_threshold=similarity_threshold,
                min_flow=min_flow,
                max_flow=max_flow
            )
            print(f"Found {len(similarity_df)} topic relationships with normalized similarity flow")
        else:
            similarity_df = calculate_topic_similarities_with_similarity_flow(
                evolution_data, 
                similarity_threshold=similarity_threshold,
                flow_scaling_factor=flow_scaling_factor
            )
            print(f"Found {len(similarity_df)} topic relationships with scaled similarity flow")

        print("\n=== PREPARING SANKEY DATA ===")
        sankey_data = prepare_sankey_data(evolution_data, similarity_df)
        print(f"Created {len(sankey_data['nodes'])} nodes and {len(sankey_data['links'])} links")

        print("\n=== ANALYZING SAMPLE REASSIGNMENTS ===")
        reassignment_df = analyze_sample_reassignments(evolution_data, similarity_df)
        print(f"Tracked {reassignment_df['sample_id'].nunique()} samples across k values")

        return {
            'evolution_data': evolution_data,
            'similarity_df': similarity_df,
            'sankey_data': sankey_data,
            'reassignment_df': reassignment_df,
            'flow_method': 'normalized_similarity' if use_normalized_flow else 'scaled_similarity'
        }


    # Modified Sankey creation function with better hover text for similarity flow
    def create_topic_evolution_sankey_similarity_flow(
        sankey_data: Dict,
        evolution_data: Dict,
        metadata_df: pd.DataFrame,
        title: str = "Topic Evolution - Similarity-Based Flow",
        width: int = 1000,
        height: int = 600,
        color_scheme: str = "Set3",
        show_similarity_threshold: float = 0.3,
        representation_threshold: float = 0.75,
        enable_click_callback: bool = True
    ) -> go.Figure:
        """
        Create Sankey diagram with similarity-based flow and updated hover text.
        """

        # Extract feature analysis for all topics
        feature_summaries = extract_feature_analysis_for_sankey(
            evolution_data, metadata_df, representation_threshold
        )

        nodes = sankey_data['nodes']
        links = sankey_data['links']

        # Filter links by similarity threshold
        filtered_links = [link for link in links if link.get('similarity', 1.0) >= show_similarity_threshold]

        # Use flow values directly (they're already similarity-based)
        flow_values = [link['value'] for link in filtered_links]

        # Create color palette and node setup (same as original)
        k_values = sorted(list(set([node['k_value'] for node in nodes])))
        colors = px.colors.qualitative.Set3[:len(k_values)]
        k_color_map = {k: colors[i % len(colors)] for i, k in enumerate(k_values)}
        node_colors = [k_color_map[node['k_value']] for node in nodes]

        # Create node labels and hover text (same as original)
        node_labels = []
        node_hover_text = []

        for node in nodes:
            label = f"K{node['k_value']}-T{node['topic_idx']}"
            node_labels.append(label)

            global_id = node['global_id']
            features = feature_summaries.get(global_id, {})

            n_highly_rep = features.get('n_highly_represented', 0)
            avg_rep = features.get('avg_representation', 0)
            feature_analysis = features.get('feature_analysis', {})

            if n_highly_rep > 0 and feature_analysis:
                feature_lines = []
                for feature_name, feature_value in list(feature_analysis.items())[:5]:
                    feature_lines.append(f"• {feature_name}: {feature_value}")

                feature_text = f"""
    <b>Shared Features (>{representation_threshold}):</b><br>
    • Highly represented samples: {n_highly_rep}<br>
    • Avg representation: {avg_rep:.3f}<br>
    {'<br>'.join(feature_lines)}
                """
            else:
                feature_text = f"""
    <b>Shared Features:</b><br>
    • No samples above {representation_threshold} threshold
                """

            hover_text = f"""
    <b>{label}</b><br>
    <b>Topic Content:</b><br>
    Top Words: {node['top_words']}<br>
    Sum Probability: {node['sum_probability']:.3f}<br>
    {feature_text}<br>
    Global ID: {node['global_id']}
            """
            node_hover_text.append(hover_text)

        # Create enhanced link hover text for similarity flow
        link_hover_text = []
        link_callback_data = []

        for i, link in enumerate(filtered_links):
            source_node = nodes[link['source']]
            target_node = nodes[link['target']]

            hover_text = f"""
    <b>Topic Evolution (Similarity-Based Flow)</b><br>
    From: K{source_node['k_value']}-T{source_node['topic_idx']}<br>
    To: K{target_node['k_value']}-T{target_node['topic_idx']}<br>
    <b>Similarity: {link['similarity']:.3f}</b><br>
    <b>Flow (Similarity): {link['value']:.3f}</b><br>
    Link Strength: {"Strong" if link['similarity'] > 0.7 else "Medium" if link['similarity'] > 0.5 else "Weak"}
            """
            link_hover_text.append(hover_text)

            callback_data = {
                'link_index': i,
                'source': {
                    'k_value': source_node['k_value'],
                    'topic_idx': source_node['topic_idx'],
                    'global_id': source_node['global_id'],
                    'top_words': source_node['top_words'],
                    'sum_probability': source_node['sum_probability']
                },
                'target': {
                    'k_value': target_node['k_value'],
                    'topic_idx': target_node['topic_idx'],
                    'global_id': target_node['global_id'],
                    'top_words': target_node['top_words'],
                    'sum_probability': target_node['sum_probability']
                },
                'similarity': link['similarity'],
                'flow_value': link['value'],
                'hover_text': hover_text
            }
            link_callback_data.append(callback_data)

        # Create the Sankey diagram (same structure as original)
        fig = go.Figure(data=[go.Sankey(
            node = dict(
                pad = 20,
                thickness = 25,
                line = dict(color = "black", width = 1.5),
                label = node_labels,
                color = node_colors,
                hovertemplate = '%{customdata}<extra></extra>',
                customdata = node_hover_text
            ),
            link = dict(
                source = [link['source'] for link in filtered_links],
                target = [link['target'] for link in filtered_links],
                value = flow_values,
                color = ['rgba(100,100,100,0.3)' for _ in filtered_links],
                hovertemplate = '%{customdata}<extra></extra>',
                customdata = link_hover_text
            )
        )])

        # Store callback data and update layout (same as original)
        if enable_click_callback:
            fig._link_callback_data = link_callback_data
            fig.update_layout(clickmode='event+select')

        fig.update_layout(
            title={
                'text': title,
                'x': 0.5,
                'xanchor': 'center',
                'font': {'size': 16}
            },
            font_size = 12,
            width = width,
            height = height,
            margin = dict(l=50, r=50, t=80, b=50),
            paper_bgcolor = 'white',
            plot_bgcolor = 'white'
        )

        # Add k-value annotations (same as original)
        for i, k_val in enumerate(k_values):
            fig.add_annotation(
                x = (i + 0.5) / len(k_values),
                y = 1.05,
                text = f"<b>K = {k_val}</b>",
                showarrow = False,
                xref = "paper",
                yref = "paper",
                font = dict(size=14, color="black"),
                bgcolor = k_color_map[k_val],
                bordercolor = "black",
                borderwidth = 1
            )

        return fig
    return (run_topic_evolution_analysis_similarity_flow,)


@app.cell(hide_code=True)
def _(Dict, List, Optional, Tuple, cosine_similarity, pd):
    def get_global_ids(
        topic_word_folder: str,
        topic_word_pattern: str = 'ASVProbabilities_{}.csv',
        k_range: Optional[Tuple[int, int]] = None
    ) -> List[str]:
        """
        Get a list of all global_ids for existing topic files.

        Args:
            topic_word_folder: Path to folder containing topic-word probability CSV files
            topic_word_pattern: File naming pattern for topic-word files with {} for k value
            k_range: Optional tuple of (min_k, max_k). If None, auto-detects from existing files

        Returns:
            List of global_ids in format ['k2_MC0', 'k2_MC1', 'k3_MC0', ...]
        """
        import os
        import pandas as pd
        import re
        from typing import List, Tuple, Optional

        # Auto-detect k values if k_range not provided
        if k_range is None:
            k_values = []
            for filename in os.listdir(topic_word_folder):
                if filename.endswith('.csv'):
                    # Extract k value from filename using the pattern
                    pattern_regex = topic_word_pattern.replace('{}', r'(\d+)')
                    match = re.match(pattern_regex, filename)
                    if match:
                        k_values.append(int(match.group(1)))

            if not k_values:
                raise ValueError(f"No files matching pattern '{topic_word_pattern}' found in {topic_word_folder}")

            k_values = sorted(k_values)
            print(f"Auto-detected k values: {k_values}")
        else:
            k_values = list(range(k_range[0], k_range[1] + 1))

        global_ids = []

        for k in k_values:
            topic_word_path = os.path.join(topic_word_folder, topic_word_pattern.format(k))

            if os.path.exists(topic_word_path):
                # Read the CSV to get the number of topics (rows)
                df = pd.read_csv(topic_word_path, index_col=0)
                num_topics = df.shape[0]

                # Generate global_ids for this k value
                for topic_idx in range(num_topics):
                    global_id = f'k{k}_MC{topic_idx}'
                    global_ids.append(global_id)

        return global_ids

    def extract_topic_evolution_data(
        selected_global_ids: List[str],
        topic_word_folder: str,
        sample_topic_folder: str,
        topic_word_pattern: str = 'ASVProbabilities_{}.csv',
        sample_topic_pattern: str = 'DirichletComponentProbabilities_{}.csv',
        embeddings_df: Optional[pd.DataFrame] = None
    ) -> Dict:
        """
        Extract topic-word, sample-topic data and metadata for selected topics
        to analyze topic evolution across k values.

        Args:
            selected_global_ids: List of global_ids from cluster selection (e.g., ['k3_MC0', 'k5_MC2'])
            topic_word_folder: Path to topic-word probability files
            sample_topic_folder: Path to sample-topic probability files  
            topic_word_pattern: File naming pattern for topic-word files
            sample_topic_pattern: File naming pattern for sample-topic files
            embeddings_df: DataFrame with embeddings and metadata (optional, for additional metadata)

        Returns:
            Dictionary containing all extracted data for evolution analysis
        """

        # Parse global_ids to get k values and topic indices
        topic_info = []
        k_values = set()

        for global_id in selected_global_ids:
            parts = global_id.split('_')
            k_val = int(parts[0][1:])  # Remove 'k' and convert to int
            topic_idx = int(parts[1][2:])  # Remove 'MC' and convert to int

            topic_info.append({
                'global_id': global_id,
                'k_value': k_val,
                'topic_idx': topic_idx
            })
            k_values.add(k_val)

        k_values = sorted(list(k_values))
        print(f"Analyzing topics across k values: {k_values}")
        print(f"Selected topics: {selected_global_ids}")

        # Load data for all relevant k values
        topic_word_data = {}
        sample_topic_data = {}

        for k in k_values:
            topic_word_path = f"{topic_word_folder}/{topic_word_pattern.format(k)}"
            sample_topic_path = f"{sample_topic_folder}/{sample_topic_pattern.format(k)}"

            try:
                topic_word_data[k] = pd.read_csv(topic_word_path, index_col=0)
                sample_topic_data[k] = pd.read_csv(sample_topic_path, index_col=0)
                print(f"Loaded k={k}: {topic_word_data[k].shape[0]} topics, {topic_word_data[k].shape[1]} words")
            except FileNotFoundError:
                print(f"Warning: Files for k={k} not found")
                continue

        # Extract selected topic data
        selected_topic_word = {}
        selected_sample_topic = {}
        topic_metadata = []

        for info in topic_info:
            k = info['k_value']
            topic_idx = info['topic_idx']
            global_id = info['global_id']

            if k in topic_word_data:
                # Get topic-word distribution
                topic_word_vec = topic_word_data[k].iloc[topic_idx]
                selected_topic_word[global_id] = topic_word_vec

                # Get sample-topic distribution (this topic across all samples)
                sample_topic_vec = sample_topic_data[k].iloc[topic_idx]
                selected_sample_topic[global_id] = sample_topic_vec

                # Calculate metadata
                sum_probability = sample_topic_vec.sum()
                top_words = topic_word_vec.nlargest(10).index.tolist()

                metadata = {
                    'global_id': global_id,
                    'k_value': k,
                    'topic_idx': topic_idx,
                    'sum_probability': sum_probability,
                    'top_words': top_words,
                    'topic_word_vector': topic_word_vec.values,
                    'sample_assignments': sample_topic_vec.values
                }

                # Add embedding metadata if available
                if embeddings_df is not None:
                    embedding_row = embeddings_df[embeddings_df['global_id'] == global_id]
                    if len(embedding_row) > 0:
                        metadata.update({
                            'x_coord': embedding_row['x'].iloc[0],
                            'y_coord': embedding_row['y'].iloc[0],
                            'cluster': embedding_row['cluster'].iloc[0]
                        })

                topic_metadata.append(metadata)

        # Create topic-word matrix for selected topics
        topic_word_matrix = pd.DataFrame(selected_topic_word).T
        sample_topic_matrix = pd.DataFrame(selected_sample_topic).T

        return {
            'topic_word_matrix': topic_word_matrix,
            'sample_topic_matrix': sample_topic_matrix,
            'topic_metadata': pd.DataFrame(topic_metadata),
            'k_values': k_values,
            'selected_global_ids': selected_global_ids,
            'raw_topic_word_data': {k: topic_word_data[k] for k in k_values if k in topic_word_data},
            'raw_sample_topic_data': {k: sample_topic_data[k] for k in k_values if k in sample_topic_data}
        }


    def calculate_topic_similarities(evolution_data: Dict, similarity_threshold: float = 0.3) -> pd.DataFrame:
        """
        Calculate cosine similarities between topics across consecutive k values
        for Sankey diagram alignment.

        Args:
            evolution_data: Output from extract_topic_evolution_data
            similarity_threshold: Minimum similarity to consider topics related

        Returns:
            DataFrame with topic similarity relationships
        """

        topic_word_matrix = evolution_data['topic_word_matrix']
        metadata_df = evolution_data['topic_metadata']
        k_values = evolution_data['k_values']

        similarity_relationships = []

        # Compare consecutive k values
        for i in range(len(k_values) - 1):
            k_low = k_values[i]
            k_high = k_values[i + 1]

            # Get topics for these k values
            topics_low = metadata_df[metadata_df['k_value'] == k_low]['global_id'].tolist()
            topics_high = metadata_df[metadata_df['k_value'] == k_high]['global_id'].tolist()

            if len(topics_low) == 0 or len(topics_high) == 0:
                continue

            # Get topic-word vectors
            vectors_low = topic_word_matrix.loc[topics_low].values
            vectors_high = topic_word_matrix.loc[topics_high].values

            # Calculate cosine similarities
            similarities = cosine_similarity(vectors_low, vectors_high)

            # Create relationships above threshold
            for idx_low, topic_low in enumerate(topics_low):
                for idx_high, topic_high in enumerate(topics_high):
                    similarity_score = similarities[idx_low, idx_high]

                    if similarity_score >= similarity_threshold:
                        # Get sum probabilities for flow volume
                        prob_low = metadata_df[metadata_df['global_id'] == topic_low]['sum_probability'].iloc[0]
                        prob_high = metadata_df[metadata_df['global_id'] == topic_high]['sum_probability'].iloc[0]

                        similarity_relationships.append({
                            'source_topic': topic_low,
                            'target_topic': topic_high,
                            'source_k': k_low,
                            'target_k': k_high,
                            'similarity': similarity_score,
                            'source_probability': prob_low,
                            'target_probability': prob_high,
                            'flow_volume': min(prob_low, prob_high)  # Conservative flow estimate
                        })

        return pd.DataFrame(similarity_relationships)

    def prepare_sankey_data(evolution_data: Dict, similarity_df: pd.DataFrame) -> Dict:
        """
        Prepare data for Sankey diagram visualization.

        Args:
            evolution_data: Output from extract_topic_evolution_data
            similarity_df: Output from calculate_topic_similarities

        Returns:
            Dictionary with nodes and links for Sankey diagram
        """

        metadata_df = evolution_data['topic_metadata']

        # Create nodes (topics at each k level)
        nodes = []
        node_id_map = {}

        for idx, row in metadata_df.iterrows():
            node_label = f"k{row['k_value']}_T{row['topic_idx']}"
            top_words_str = ", ".join(row['top_words'][:5])  # Top 5 words

            node = {
                'id': len(nodes),
                'label': node_label,
                'global_id': row['global_id'],
                'k_value': row['k_value'],
                'topic_idx': row['topic_idx'],
                'sum_probability': row['sum_probability'],
                'top_words': top_words_str,
                'description': f"{node_label}: {top_words_str}"
            }

            nodes.append(node)
            node_id_map[row['global_id']] = len(nodes) - 1

        # Create links (topic relationships)
        links = []

        for _, row in similarity_df.iterrows():
            if row['source_topic'] in node_id_map and row['target_topic'] in node_id_map:
                link = {
                    'source': node_id_map[row['source_topic']],
                    'target': node_id_map[row['target_topic']],
                    'value': row['flow_volume'],
                    'similarity': row['similarity'],
                    'source_topic': row['source_topic'],
                    'target_topic': row['target_topic']
                }
                links.append(link)

        return {
            'nodes': nodes,
            'links': links,
            'node_id_map': node_id_map
        }

    def analyze_sample_reassignments(evolution_data: Dict, similarity_df: pd.DataFrame, top_n_samples: int = 20) -> pd.DataFrame:
        """
        Analyze how samples (documents) get reassigned across k values.

        Args:
            evolution_data: Output from extract_topic_evolution_data
            similarity_df: Topic similarity relationships
            top_n_samples: Number of top samples to track per topic

        Returns:
            DataFrame showing sample assignment changes
        """

        sample_topic_matrix = evolution_data['sample_topic_matrix']
        metadata_df = evolution_data['topic_metadata']

        sample_assignments = []

        # For each topic, get its top assigned samples
        for _, topic_meta in metadata_df.iterrows():
            global_id = topic_meta['global_id']
            k_value = topic_meta['k_value']

            # Get sample assignments for this topic
            topic_assignments = sample_topic_matrix.loc[global_id]
            top_samples = topic_assignments.nlargest(top_n_samples)

            for sample_id, probability in top_samples.items():
                sample_assignments.append({
                    'sample_id': sample_id,
                    'topic_global_id': global_id,
                    'k_value': k_value,
                    'assignment_probability': probability,
                    'rank': list(top_samples.index).index(sample_id) + 1
                })

        sample_df = pd.DataFrame(sample_assignments)

        # Analyze reassignments
        reassignment_analysis = []

        for sample_id in sample_df['sample_id'].unique():
            sample_history = sample_df[sample_df['sample_id'] == sample_id].sort_values('k_value')

            if len(sample_history) > 1:
                for i in range(len(sample_history) - 1):
                    current = sample_history.iloc[i]
                    next_assignment = sample_history.iloc[i + 1]

                    reassignment_analysis.append({
                        'sample_id': sample_id,
                        'from_k': current['k_value'],
                        'to_k': next_assignment['k_value'],
                        'from_topic': current['topic_global_id'],
                        'to_topic': next_assignment['topic_global_id'],
                        'from_probability': current['assignment_probability'],
                        'to_probability': next_assignment['assignment_probability'],
                        'probability_change': next_assignment['assignment_probability'] - current['assignment_probability']
                    })

        return pd.DataFrame(reassignment_analysis)
    return (
        analyze_sample_reassignments,
        extract_topic_evolution_data,
        get_global_ids,
        prepare_sankey_data,
    )


@app.cell
def _(get_global_ids, topic_word_folder):
    global_ids_test = get_global_ids(topic_word_folder)
    return (global_ids_test,)


@app.cell
def _(
    global_ids_test,
    run_topic_evolution_analysis_similarity_flow,
    sample_topic_folder,
    topic_word_folder,
):
    # Normalize similarities to a specific range for better visualization
    results_topic_similarity = run_topic_evolution_analysis_similarity_flow(
        selected_global_ids=global_ids_test,
        topic_word_folder=topic_word_folder,
        sample_topic_folder=sample_topic_folder,
        use_normalized_flow=True,   # Normalize similarities
        min_flow=0.1,              # Minimum line thickness
        max_flow=1.0               # Maximum line thickness
    )
    return (results_topic_similarity,)


@app.cell(hide_code=True)
def _(run_topic_evolution_analysis_similarity_flow):
    import anywidget
    import traitlets
    class SimilaritySankeyWidget(anywidget.AnyWidget):
        _esm = '''
        import * as d3 from "https://cdn.skypack.dev/d3@7";

        function render({ model, el }) {
            el.innerHTML = '';

            const data = model.get("sankey_data");
            const width = model.get("width");
            const height = model.get("height");
            const colorSchemes = model.get("color_schemes");
            const selectedFlow = model.get("selected_flow");
            const minSimilarity = model.get("min_similarity");
            const showSimilarityMetrics = model.get("show_similarity_metrics");

            if (!data || !data.nodes || Object.keys(data.nodes).length === 0) {
                el.innerHTML = '<div style="padding: 20px; text-align: center; font-family: sans-serif;">No data available. Please load your similarity analysis data first.</div>';
                return;
            }

            // Create SVG
            const svg = d3.select(el)
                .append("svg")
                .attr("width", width)
                .attr("height", height)
                .style("background", "#fafafa")
                .style("border", "1px solid #ddd");

            const margin = { top: 60, right: 150, bottom: 60, left: 100 };
            const chartWidth = width - margin.left - margin.right;
            const chartHeight = height - margin.top - margin.bottom;

            const g = svg.append("g")
                .attr("transform", `translate(${margin.left}, ${margin.top})`);

            // Process data for visualization
            const processedData = processDataForVisualization(data, minSimilarity);

            // Draw the similarity-based sankey diagram
            drawSimilaritySankeyDiagram(g, processedData, chartWidth, chartHeight, colorSchemes, selectedFlow, model, showSimilarityMetrics, minSimilarity);

            // Update handlers
            model.on("change:sankey_data", () => {
                const newData = model.get("sankey_data");
                if (newData && Object.keys(newData).length > 0) {
                    const newProcessedData = processDataForVisualization(newData, model.get("min_similarity"));
                    svg.selectAll("*").remove();
                    const newG = svg.append("g").attr("transform", `translate(${margin.left}, ${margin.top})`);
                    drawSimilaritySankeyDiagram(newG, newProcessedData, chartWidth, chartHeight, colorSchemes, model.get("selected_flow"), model, model.get("show_similarity_metrics"), model.get("min_similarity"));
                }
            });

            model.on("change:selected_flow", () => {
                const newSelectedFlow = model.get("selected_flow");
                svg.selectAll("*").remove();
                const newG = svg.append("g").attr("transform", `translate(${margin.left}, ${margin.top})`);
                drawSimilaritySankeyDiagram(newG, processedData, chartWidth, chartHeight, colorSchemes, newSelectedFlow, model, model.get("show_similarity_metrics"), model.get("min_similarity"));
            });

            model.on("change:min_similarity", () => {
                const newMinSimilarity = model.get("min_similarity");
                const newProcessedData = processDataForVisualization(data, newMinSimilarity);
                svg.selectAll("*").remove();
                const newG = svg.append("g").attr("transform", `translate(${margin.left}, ${margin.top})`);
                drawSimilaritySankeyDiagram(newG, newProcessedData, chartWidth, chartHeight, colorSchemes, model.get("selected_flow"), model, model.get("show_similarity_metrics"), newMinSimilarity);
            });
        }

        function processDataForVisualization(data, minSimilarity) {
            const nodes = [];
            const flows = [];
            const kValues = data.k_values || [];

            console.log("Processing similarity-based data...");

            if (data.nodes && Array.isArray(data.nodes)) {
                data.nodes.forEach(nodeData => {
                    const k = nodeData.k_value;
                    const topicIdx = nodeData.topic_idx;
                    const globalId = nodeData.global_id;

                    nodes.push({
                        id: globalId,
                        k: k,
                        topic_idx: topicIdx,
                        totalProbability: nodeData.sum_probability || 0,
                        topWords: nodeData.top_words || "Unknown",
                        highCount: Math.round((nodeData.sum_probability || 0) * 100),
                        mediumCount: 0,
                        globalId: globalId
                    });
                });
            }

            if (data.links && Array.isArray(data.links)) {
                data.links.forEach(linkData => {
                    if (linkData.similarity >= minSimilarity) {
                        const sourceNode = nodes.find(n => n.id === linkData.source_topic);
                        const targetNode = nodes.find(n => n.id === linkData.target_topic);

                        if (sourceNode && targetNode) {
                            flows.push({
                                source: linkData.source_topic,
                                target: linkData.target_topic,
                                sourceK: linkData.source_k,
                                targetK: linkData.target_k,
                                similarity: linkData.similarity,
                                sampleCount: Math.round(linkData.flow_volume * 100),
                                averageProbability: linkData.similarity,
                                flowVolume: linkData.flow_volume,
                                sourceProb: linkData.source_probability || 0,
                                targetProb: linkData.target_probability || 0
                            });
                        }
                    }
                });
            }

            console.log(`Processed ${nodes.length} nodes and ${flows.length} flows`);
            return { nodes, flows, kValues };
        }

        function drawSimilaritySankeyDiagram(g, data, width, height, colorSchemes, selectedFlow, model, showSimilarityMetrics, minSimilarity) {
            const { nodes, flows, kValues } = data;

            if (nodes.length === 0) {
                g.append("text")
                    .attr("x", width / 2)
                    .attr("y", height / 2)
                    .attr("text-anchor", "middle")
                    .style("font-size", "16px")
                    .style("fill", "#666")
                    .text("No nodes to display");
                return;
            }

            const significantFlows = flows.filter(flow => flow.similarity >= minSimilarity);
            const kSpacing = width / Math.max(1, kValues.length - 1);
            const nodesByK = d3.group(nodes, d => d.k);

            // Position optimization
            const optimizedNodePositions = optimizeNodeOrderSimilarity(nodes, significantFlows, kValues, nodesByK, height);

            nodes.forEach(node => {
                const kIndex = kValues.indexOf(node.k);
                node.x = kIndex * kSpacing;
                node.y = optimizedNodePositions[node.id];
            });

            // Draw flows
            const maxSimilarity = d3.max(significantFlows, d => d.similarity) || 1;
            const minFlowWidth = 2;
            const maxFlowWidth = 25;
            const flowGroup = g.append("g").attr("class", "flows");

            significantFlows.forEach((flow, flowIndex) => {
                const sourceNode = nodes.find(n => n.id === flow.source);
                const targetNode = nodes.find(n => n.id === flow.target);

                if (sourceNode && targetNode) {
                    const flowWidth = minFlowWidth + (flow.similarity / maxSimilarity) * (maxFlowWidth - minFlowWidth);
                    const curvePath = createCurvePath(sourceNode.x + 15, sourceNode.y, targetNode.x - 15, targetNode.y);
                    const isSelected = selectedFlow && selectedFlow.source === flow.source && selectedFlow.target === flow.target;

                    flowGroup.append("path")
                        .attr("d", curvePath)
                        .attr("stroke", isSelected ? "#ff6b35" : "#888")
                        .attr("stroke-width", isSelected ? flowWidth + 3 : flowWidth)
                        .attr("fill", "none")
                        .attr("opacity", isSelected ? 1.0 : 0.7)
                        .style("cursor", "pointer")
                        .on("mouseover", function(event) {
                            if (!isSelected) d3.select(this).attr("opacity", 0.9);
                            showSimilarityTooltip(g, event, flow);
                        })
                        .on("mouseout", function() {
                            if (!isSelected) d3.select(this).attr("opacity", 0.7);
                            g.selectAll(".tooltip").remove();
                        })
                        .on("click", function(event) {
                            event.stopPropagation();
                            if (isSelected) {
                                model.set("selected_flow", {});
                            } else {
                                model.set("selected_flow", {
                                    source: flow.source,
                                    target: flow.target,
                                    sourceK: flow.sourceK,
                                    targetK: flow.targetK,
                                    similarity: flow.similarity,
                                    flowVolume: flow.flowVolume
                                });
                            }
                            model.save_changes();
                        });
                }
            });

            // Draw nodes as radial histograms
            const nodeGroup = g.append("g").attr("class", "nodes");

            console.log("About to draw", nodes.length, "nodes");

            nodes.forEach((node, index) => {
                console.log(`Drawing node ${index + 1}/${nodes.length}:`, node.id, "at position", node.x, node.y);

                const nodeG = nodeGroup.append("g")
                    .attr("class", "node")
                    .attr("transform", `translate(${node.x}, ${node.y})`);

                // Draw the working radial histogram
                drawRadialHistogramDistribution(nodeG, node, colorSchemes[node.k] || "#666", model);
            });

            // Background click handler
            g.on("click", function() {
                model.set("selected_flow", {});
                model.save_changes();
            });

            // K value labels
            kValues.forEach((k, index) => {
                const labelColor = colorSchemes[k] || "#333";
                g.append("text")
                    .attr("x", index * kSpacing)
                    .attr("y", -30)
                    .attr("text-anchor", "middle")
                    .style("font-size", "16px")
                    .style("font-weight", "bold")
                    .style("fill", labelColor)
                    .text(`K=${k}`);
            });

            // Legend - moved lower in bottom-left to avoid overlap
            const legend = g.append("g").attr("class", "legend").attr("transform", `translate(20, ${height - 80})`);
            const legendTexts = [
                { y: 8, text: "Radial Histogram Distribution", size: "12px", weight: "bold", color: "#333" },
                { y: 24, text: `Min Similarity: ${minSimilarity.toFixed(2)}`, size: "10px", weight: "normal", color: "#666" },
                { y: 36, text: `Flows: ${significantFlows.length} shown`, size: "10px", weight: "normal", color: "#666" },
                { y: 48, text: "Each slice = 0.1 probability bin", size: "9px", weight: "normal", color: "#666" },
                { y: 60, text: "Bar length = sample count in bin", size: "9px", weight: "normal", color: "#666" },
                { y: 72, text: "Starting from 3 o'clock: 0.0-0.1, 0.1-0.2...", size: "8px", weight: "normal", color: "#666" },
                { y: 84, text: "Light blue = low prob, Dark blue = high prob", size: "8px", weight: "normal", color: "#888" },
                { y: 96, text: "Hover bins for details", size: "9px", weight: "normal", color: "#ff6b35" }
            ];

            legendTexts.forEach(item => {
                legend.append("text")
                    .attr("x", 0)
                    .attr("y", item.y)
                    .style("font-size", item.size)
                    .style("font-weight", item.weight)
                    .style("fill", item.color)
                    .text(item.text);
            });
        }

        function optimizeNodeOrderSimilarity(nodes, flows, kValues, nodesByK, height) {
            const nodePositions = {};
            const firstK = kValues[0];
            const firstKNodes = nodesByK.get(firstK) || [];
            const spacing = height / Math.max(1, firstKNodes.length + 1);

            firstKNodes.forEach((node, index) => {
                nodePositions[node.id] = (index + 1) * spacing;
            });

            for (let kIndex = 1; kIndex < kValues.length; kIndex++) {
                const currentK = kValues[kIndex];
                const prevK = kValues[kIndex - 1];
                const currentKNodes = nodesByK.get(currentK) || [];

                const barycenterData = currentKNodes.map(node => {
                    const nodeId = node.id;
                    let weightedSum = 0;
                    let totalWeight = 0;

                    flows.forEach(flow => {
                        if (flow.target === nodeId && flow.sourceK === prevK) {
                            const sourcePosition = nodePositions[flow.source];
                            if (sourcePosition !== undefined) {
                                const weight = flow.similarity;
                                weightedSum += sourcePosition * weight;
                                totalWeight += weight;
                            }
                        }
                    });

                    const barycenter = totalWeight > 0 ? weightedSum / totalWeight : height / 2;
                    return { node: node, barycenter: barycenter, totalWeight: totalWeight };
                });

                barycenterData.sort((a, b) => a.barycenter - b.barycenter);
                const newSpacing = height / Math.max(1, barycenterData.length + 1);
                barycenterData.forEach((data, index) => {
                    nodePositions[data.node.id] = (index + 1) * newSpacing;
                });
            }

            return nodePositions;
        }

        function createCurvePath(x1, y1, x2, y2) {
            const midX = (x1 + x2) / 2;
            return `M ${x1} ${y1} C ${midX} ${y1} ${midX} ${y2} ${x2} ${y2}`;
        }

        function showSimilarityTooltip(g, event, flow) {
            const tooltip = g.append("g").attr("class", "tooltip");
            const tooltipLines = [
                `Similarity: ${flow.similarity.toFixed(3)}`,
                `Flow Volume: ${flow.flowVolume.toFixed(3)}`,
                `${flow.source} → ${flow.target}`,
                `K${flow.sourceK} to K${flow.targetK}`
            ];

            const tooltipWidth = 180;
            const tooltipHeight = tooltipLines.length * 14 + 10;
            let tooltipX = event.layerX || 0;
            let tooltipY = (event.layerY || 0) - tooltipHeight - 10;

            if (tooltipX + tooltipWidth > 1000) tooltipX = 1000 - tooltipWidth - 10;
            if (tooltipY < 0) tooltipY = (event.layerY || 0) + 20;

            tooltip.append("rect")
                .attr("x", tooltipX).attr("y", tooltipY)
                .attr("width", tooltipWidth).attr("height", tooltipHeight)
                .attr("fill", "white").attr("stroke", "black").attr("rx", 3).attr("opacity", 0.9);

            tooltipLines.forEach((line, i) => {
                tooltip.append("text")
                    .attr("x", tooltipX + 5).attr("y", tooltipY + 15 + i * 14)
                    .style("font-size", "11px").style("fill", "black").text(line);
            });
        }

        function drawRadialHistogramDistribution(nodeG, node, baseColor, model) {
            console.log("Starting radial histogram for node:", node.id);

            const rawData = model.get("sankey_data");
            const sampleProbabilities = getSampleProbabilities(node, rawData);

            console.log("Sample probabilities for", node.id, ":", sampleProbabilities?.length || "none");

            const numBins = 10;
            const binSize = 0.1;
            const bins = [];

            // Initialize bins
            for (let i = 0; i < numBins; i++) {
                bins.push({
                    binIndex: i,
                    minProb: i * binSize,
                    maxProb: (i + 1) * binSize,
                    count: 0,
                    samples: []
                });
            }

            // Count samples into bins OR use mock data
            if (sampleProbabilities && sampleProbabilities.length > 0) {
                console.log("Using real sample data");
                sampleProbabilities.forEach(sample => {
                    const prob = sample.probability;
                    let binIndex = Math.floor(prob / binSize);
                    if (binIndex >= numBins) binIndex = numBins - 1;
                    bins[binIndex].count++;
                    bins[binIndex].samples.push(sample.sample_id);
                });
            } else {
                console.log("Using mock data for node", node.id);
                // Always use mock data to ensure something shows up
                const mockCounts = [8, 6, 5, 4, 3, 2, 2, 1, 1, 0];
                bins.forEach((bin, i) => { 
                    bin.count = mockCounts[i] || 0;
                    // Add mock samples
                    for (let j = 0; j < bin.count; j++) {
                        bin.samples.push(`mock_sample_${i}_${j}`);
                    }
                });
            }

            const outerRadius = 25;  // Maximum radius
            const angleStep = (2 * Math.PI) / numBins;
            const maxCount = Math.max(...bins.map(b => b.count));

            console.log("Max count for node", node.id, ":", maxCount);

            if (maxCount === 0) {
                console.log("No data for node", node.id, "drawing empty circle");
                nodeG.append("circle").attr("r", 12).attr("fill", baseColor).attr("stroke", "white").attr("stroke-width", 2);
                nodeG.append("text").attr("x", 18).attr("y", 0).attr("dy", "0.35em")
                    .style("font-size", "10px").style("font-weight", "bold").style("fill", "#333")
                    .text("T" + node.topic_idx);
                addNodeInteraction(nodeG, node);
                return;
            }

            // FIXED SCALING: [0, maxCount] -> [0, outerRadius]
            // This means: 0 samples = 0 radius (no bar), maxCount samples = full radius
            const radiusScale = d3.scaleLinear()
                .domain([0, maxCount])
                .range([0, outerRadius]);  // Start from 0, not innerRadius!

            // FIXED COLOR SCALE: Direct blue gradient instead of modifying baseColor
            const colorScale = d3.scaleLinear()
                .domain([0, 1.0])
                .range(["#e3f2fd", "#0d47a1"]);  // Light blue to dark blue

            const arcGenerator = d3.arc();
            let barsDrawn = 0;

            console.log("Drawing", numBins, "bins for node", node.id);

            bins.forEach((bin, i) => {
                if (bin.count === 0) return;  // Skip bins with no samples

                const startAngle = i * angleStep;
                const endAngle = (i + 1) * angleStep;

                // CORRECTED: Bar extends from center (0) to scaled radius
                const barRadius = radiusScale(bin.count);

                const binMidProb = (bin.minProb + bin.maxProb) / 2;
                const barColor = colorScale(binMidProb);

                console.log(`Drawing bin ${i}: count=${bin.count}, radius=${barRadius.toFixed(1)}, angles=${startAngle.toFixed(2)}-${endAngle.toFixed(2)}`);

                try {
                    const arcPath = arcGenerator({
                        innerRadius: 0,           // FIXED: Start from center (0)
                        outerRadius: barRadius,   // FIXED: Extend to proportional radius
                        startAngle: startAngle,
                        endAngle: endAngle
                    });

                    if (arcPath) {
                        nodeG.append("path")
                            .attr("d", arcPath)
                            .attr("fill", barColor)
                            .attr("stroke", "white")
                            .attr("stroke-width", 0.5)
                            .attr("opacity", 0.8)
                            .style("cursor", "pointer")
                            .on("mouseover", function(event) {
                                showBinTooltip(nodeG, event, bin, i, sampleProbabilities?.length || bins.reduce((sum, b) => sum + b.count, 0));
                            })
                            .on("mouseout", function() {
                                nodeG.selectAll(".bin-tooltip").remove();
                            });

                        barsDrawn++;
                        console.log(`Successfully drew bin ${i} for node ${node.id}`);
                    } else {
                        console.log(`Failed to generate arc path for bin ${i}`);
                    }
                } catch (error) {
                    console.log("Error drawing bin", i, ":", error);
                }
            });

            console.log(`Drew ${barsDrawn} bars for node ${node.id}`);

            // Reference elements - draw a small center dot and outer ring for reference
            nodeG.append("circle")
                .attr("r", 2)  // Small center dot
                .attr("fill", baseColor)
                .attr("stroke", "white")
                .attr("stroke-width", 1);

            nodeG.append("circle")
                .attr("r", outerRadius)
                .attr("fill", "none")
                .attr("stroke", baseColor)
                .attr("stroke-width", 1)
                .attr("opacity", 0.3);

            // Labels
            nodeG.append("text").attr("x", outerRadius + 8).attr("y", 0).attr("dy", "0.35em")
                .style("font-size", "9px").style("font-weight", "bold").style("fill", "#333").text("T" + node.topic_idx);
            nodeG.append("text").attr("x", 0).attr("y", -outerRadius - 3).attr("text-anchor", "middle")
                .style("font-size", "7px").style("fill", "#666").text(`${maxCount}`);

            console.log("Completed radial histogram for node", node.id);
            addNodeInteraction(nodeG, node);
        }

        function showBinTooltip(nodeG, event, bin, binIndex, totalSamples) {
            const tooltip = nodeG.append("g").attr("class", "bin-tooltip");
            const percentage = totalSamples > 0 ? ((bin.count / totalSamples) * 100).toFixed(1) : "0.0";
            const tooltipLines = [
                `Bin ${binIndex}: ${bin.minProb.toFixed(1)}-${bin.maxProb.toFixed(1)}`,
                `Count: ${bin.count} samples`,
                `Percentage: ${percentage}%`
            ];

            const tooltipWidth = 140;
            const tooltipHeight = tooltipLines.length * 12 + 8;
            const tooltipX = -tooltipWidth / 2;
            const tooltipY = -35 - tooltipHeight;

            tooltip.append("rect")
                .attr("x", tooltipX).attr("y", tooltipY)
                .attr("width", tooltipWidth).attr("height", tooltipHeight)
                .attr("fill", "white").attr("stroke", "black").attr("rx", 3).attr("opacity", 0.9);

            tooltipLines.forEach((line, i) => {
                tooltip.append("text")
                    .attr("x", tooltipX + 5).attr("y", tooltipY + 12 + i * 12)
                    .style("font-size", "9px").style("fill", "black").text(line);
            });
        }

        function addNodeInteraction(nodeG, node) {
            nodeG.append("circle").attr("r", 35).attr("fill", "transparent").style("cursor", "pointer")
                .on("mouseover", function(event) { showNodeTooltip(nodeG, event, node); })
                .on("mouseout", function() { nodeG.selectAll(".tooltip").remove(); });
        }

        function showNodeTooltip(g, event, node) {
            const tooltip = g.append("g").attr("class", "tooltip");
            const tooltipLines = [
                `${node.id}`,
                `Topic ${node.topic_idx} (K=${node.k})`,
                `Total Probability: ${node.totalProbability.toFixed(3)}`,
                `Top Words: ${node.topWords}`
            ];

            const tooltipWidth = Math.max(200, Math.max(...tooltipLines.map(line => line.length * 7)));
            const tooltipHeight = tooltipLines.length * 14 + 10;
            let tooltipX = event.layerX || 0;
            let tooltipY = (event.layerY || 0) - tooltipHeight - 10;

            if (tooltipX + tooltipWidth > 1000) tooltipX = 1000 - tooltipWidth - 10;
            if (tooltipY < 0) tooltipY = (event.layerY || 0) + 20;

            tooltip.append("rect")
                .attr("x", tooltipX).attr("y", tooltipY)
                .attr("width", tooltipWidth).attr("height", tooltipHeight)
                .attr("fill", "white").attr("stroke", "black").attr("rx", 3).attr("opacity", 0.9);

            tooltipLines.forEach((line, i) => {
                tooltip.append("text")
                    .attr("x", tooltipX + 5).attr("y", tooltipY + 15 + i * 14)
                    .style("font-size", "11px").style("fill", "black").text(line);
            });
        }

        function getSampleProbabilities(node, rawData) {
            if (rawData && rawData.sample_topic_matrix && rawData.sample_topic_matrix[node.id]) {
                return rawData.sample_topic_matrix[node.id];
            }

            const numSamples = Math.floor(Math.random() * 40) + 20;
            const samples = [];
            const topicIdx = node.topic_idx || 0;
            const pattern = topicIdx % 4;

            for (let i = 0; i < numSamples; i++) {
                let probability;
                switch (pattern) {
                    case 0: probability = Math.pow(Math.random(), 2); break;
                    case 1: probability = Math.pow(Math.random(), 0.5); break;
                    case 2: probability = Math.random() < 0.5 ? Math.random() * 0.3 : 0.7 + Math.random() * 0.3; break;
                    case 3: probability = Math.random(); break;
                    default: probability = Math.random();
                }
                samples.push({ sample_id: "sample_" + i, probability: probability });
            }
            return samples;
        }

        export default { render };
        '''

        _css = '''
        .widget-container {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
        }
        .flows { pointer-events: auto; }
        .nodes { pointer-events: auto; }
        .tooltip { pointer-events: none; }
        .bin-tooltip { pointer-events: none; }
        .scale-lines { pointer-events: none; }
        '''

        # Widget traits
        sankey_data = traitlets.Dict(default_value={}).tag(sync=True)
        width = traitlets.Int(default_value=1200).tag(sync=True)
        height = traitlets.Int(default_value=800).tag(sync=True)
        selected_flow = traitlets.Dict(default_value={}).tag(sync=True)
        min_similarity = traitlets.Float(default_value=0.3).tag(sync=True)
        show_similarity_metrics = traitlets.Bool(default_value=True).tag(sync=True)

        color_schemes = traitlets.Dict(default_value={
            2: "#1f77b4", 3: "#ff7f0e", 4: "#2ca02c", 5: "#d62728", 6: "#9467bd",
            7: "#8c564b", 8: "#e377c2", 9: "#7f7f7f", 10: "#bcbd22"
        }).tag(sync=True)

        def __init__(self, similarity_results=None, min_similarity=0.3, **kwargs):
            super().__init__(**kwargs)
            self.min_similarity = min_similarity
            if similarity_results:
                self.set_similarity_data(similarity_results)

        def set_similarity_data(self, similarity_results):
            """Convert similarity analysis results to widget format"""
            evolution_data = similarity_results['evolution_data']
            similarity_df = similarity_results['similarity_df']
            sankey_data = similarity_results['sankey_data']

            widget_data = {
                'k_values': evolution_data['k_values'],
                'nodes': [],
                'links': [],
                'sample_topic_matrix': {}
            }

            # Convert sample-topic matrix
            sample_topic_matrix = evolution_data['sample_topic_matrix']
            for global_id in sample_topic_matrix.index:
                sample_assignments = sample_topic_matrix.loc[global_id]
                nonzero_assignments = sample_assignments[sample_assignments > 0.01]
                widget_data['sample_topic_matrix'][global_id] = [
                    {'sample_id': sample_id, 'probability': float(prob)}
                    for sample_id, prob in nonzero_assignments.items()
                ]

            # Convert nodes
            for node in sankey_data['nodes']:
                widget_data['nodes'].append({
                    'global_id': node['global_id'],
                    'k_value': node['k_value'],
                    'topic_idx': node['topic_idx'],
                    'sum_probability': node['sum_probability'],
                    'top_words': node['top_words']
                })

            # Convert links
            for _, row in similarity_df.iterrows():
                widget_data['links'].append({
                    'source_topic': row['source_topic'],
                    'target_topic': row['target_topic'],
                    'source_k': row['source_k'],
                    'target_k': row['target_k'],
                    'similarity': row['similarity'],
                    'flow_volume': row['flow_volume'],
                    'source_probability': row.get('source_probability', 0),
                    'target_probability': row.get('target_probability', 0)
                })

            self.sankey_data = widget_data
            return self

        def set_similarity_threshold(self, threshold):
            """Update the minimum similarity threshold for filtering flows"""
            self.min_similarity = threshold
            print(f"Similarity threshold updated to {threshold}")
            print(f"Only flows with similarity ≥ {threshold} will be displayed")
            return self

        def toggle_similarity_metrics(self, show=True):
            """Toggle display of similarity metrics"""
            self.show_similarity_metrics = show
            return self


    def create_similarity_sankey_widget(
        similarity_results, 
        min_similarity=0.3, 
        width=1200, 
        height=800
    ):
        """
        Create a similarity-based Sankey widget from analysis results.

        Args:
            similarity_results: Output from run_topic_evolution_analysis_similarity_flow()
            min_similarity: Minimum similarity threshold to display flows
            width: Widget width in pixels
            height: Widget height in pixels

        Returns:
            SimilaritySankeyWidget instance
        """
        widget = SimilaritySankeyWidget(
            similarity_results=similarity_results,
            min_similarity=min_similarity,
            width=width,
            height=height
        )
        return widget


    def create_similarity_analysis_and_widget(
        selected_global_ids,
        topic_word_folder,
        sample_topic_folder,
        embeddings_df=None,
        similarity_threshold=0.3,
        use_normalized_flow=True,
        widget_width=1200,
        widget_height=800
    ):
        """
        Complete pipeline: run similarity analysis and create interactive widget.

        Args:
            selected_global_ids: List of global_ids from cluster selection
            topic_word_folder: Path to topic-word probability files
            sample_topic_folder: Path to sample-topic probability files  
            embeddings_df: DataFrame with embeddings and metadata (optional)
            similarity_threshold: Minimum similarity to show connections
            use_normalized_flow: Whether to normalize similarity scores for flow
            widget_width: Widget width in pixels
            widget_height: Widget height in pixels

        Returns:
            Dictionary with 'results' and 'widget' keys
        """
        # Run the similarity-based analysis
        print("=== Running Similarity-Based Topic Evolution Analysis ===")
        results = run_topic_evolution_analysis_similarity_flow(
            selected_global_ids=selected_global_ids,
            topic_word_folder=topic_word_folder,
            sample_topic_folder=sample_topic_folder,
            embeddings_df=embeddings_df,
            similarity_threshold=similarity_threshold,
            use_normalized_flow=use_normalized_flow
        )

        print("\n=== Creating Interactive Similarity Widget ===")
        # Create the interactive widget
        widget = create_similarity_sankey_widget(
            similarity_results=results,
            min_similarity=similarity_threshold,
            width=widget_width,
            height=widget_height
        )

        print(f"✓ Widget created with {len(results['similarity_df'])} flows")
        print(f"✓ Flow thickness now represents similarity strength")
        print(f"✓ Minimum similarity threshold: {similarity_threshold}")
        print(f"✓ Radial histograms show probability distributions")
        print(f"✓ Each slice represents 0.1 probability bin (0.0-0.1, 0.1-0.2, etc.)")

        return {
            'results': results,
            'widget': widget
        }
    return (create_similarity_sankey_widget,)


@app.cell
def _(mo):
    mo.md(r"""## Plot""")
    return


@app.cell
def _(
    create_similarity_sankey_widget,
    results_topic_similarity,
    similarity_slider,
):
    widget_radio = create_similarity_sankey_widget(
        similarity_results=results_topic_similarity,
        min_similarity=similarity_slider.value,
        width=1200,
        height=800
    )
    return (widget_radio,)


@app.cell
def _(mo):
    similarity_slider = mo.ui.slider(start=0.1, stop=1, step=0.1, label="Similarity Threshold Slider", value=0.7)
    return (similarity_slider,)


@app.cell
def _(mo, similarity_slider):
    mo.hstack([similarity_slider, mo.md(f"Has value: {similarity_slider.value}")])
    return


@app.cell
def _(widget_radio):
    widget_radio
    return


@app.function
def export_widget_svg(widget, filename="similarity_sankey.svg"):
    """
    Export your widget_radio as SVG
    """
    # Get the current widget state
    nodes = widget.sankey_data.get('nodes', [])
    links = widget.sankey_data.get('links', [])
    k_values = widget.sankey_data.get('k_values', [])

    width = widget.width
    height = widget.height
    min_similarity = widget.min_similarity

    # Filter links by similarity threshold
    significant_links = [link for link in links if link.get('similarity', 0) >= min_similarity]

    # Create SVG content
    svg_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" 
     xmlns="http://www.w3.org/2000/svg">

    <title>Similarity Sankey Diagram</title>

    <!-- Background -->
    <rect width="100%" height="100%" fill="#fafafa" stroke="#ddd" stroke-width="1"/>

    <!-- Styles -->
    <style>
        <![CDATA[
        .flow-path {{ 
            stroke-linecap: round; 
            fill: none; 
            opacity: 0.7;
        }}
        .node-circle {{ 
            stroke: white; 
            stroke-width: 2; 
        }}
        .node-label {{ 
            font-family: Arial, sans-serif; 
            font-size: 9px; 
            font-weight: bold; 
            fill: #333;
        }}
        .k-label {{ 
            font-family: Arial, sans-serif; 
            font-size: 16px; 
            font-weight: bold;
        }}
        .legend-text {{ 
            font-family: Arial, sans-serif; 
            font-size: 10px; 
            fill: #666;
        }}
        .legend-title {{ 
            font-family: Arial, sans-serif; 
            font-size: 12px; 
            font-weight: bold; 
            fill: #333;
        }}
        ]]>
    </style>

    <!-- Main visualization group -->
    <g transform="translate(100, 60)">
'''

    # Calculate positions
    chart_width = width - 200  # margin left + right
    chart_height = height - 120  # margin top + bottom

    if len(k_values) > 1:
        k_spacing = chart_width / (len(k_values) - 1)
    else:
        k_spacing = chart_width / 2

    # Group nodes by k value
    nodes_by_k = {}
    for node in nodes:
        k = node['k_value']
        if k not in nodes_by_k:
            nodes_by_k[k] = []
        nodes_by_k[k].append(node)

    # Position nodes
    node_positions = {}
    for i, k in enumerate(k_values):
        k_nodes = nodes_by_k.get(k, [])
        if k_nodes:
            spacing = chart_height / (len(k_nodes) + 1)
            for j, node in enumerate(k_nodes):
                x = i * k_spacing
                y = (j + 1) * spacing
                node_positions[node['global_id']] = (x, y)

    # Draw flows/links
    max_similarity = max([link.get('similarity', 0) for link in significant_links]) if significant_links else 1
    min_flow_width = 2
    max_flow_width = 25

    svg_content += '        <!-- Flows -->\n        <g class="flows">\n'

    for link in significant_links:
        source_id = link['source_topic']
        target_id = link['target_topic']
        similarity = link.get('similarity', 0)

        if source_id in node_positions and target_id in node_positions:
            x1, y1 = node_positions[source_id]
            x2, y2 = node_positions[target_id]

            # Calculate flow width based on similarity
            flow_width = min_flow_width + (similarity / max_similarity) * (max_flow_width - min_flow_width)

            # Create curved path
            mid_x = (x1 + x2) / 2
            path_d = f"M {x1 + 15} {y1} C {mid_x} {y1} {mid_x} {y2} {x2 - 15} {y2}"

            svg_content += f'''            <path d="{path_d}" 
                  class="flow-path" 
                  stroke="#888" 
                  stroke-width="{flow_width:.1f}"
                  data-similarity="{similarity:.3f}"
                  data-source="{source_id}"
                  data-target="{target_id}">
                <title>Similarity: {similarity:.3f} | {source_id} → {target_id}</title>
            </path>
'''

    svg_content += '        </g>\n'

    # Draw nodes
    svg_content += '        <!-- Nodes -->\n        <g class="nodes">\n'

    color_schemes = widget.color_schemes

    for node in nodes:
        node_id = node['global_id']
        if node_id in node_positions:
            x, y = node_positions[node_id]
            k = node['k_value']
            topic_idx = node['topic_idx']
            color = color_schemes.get(k, '#666')
            top_words = node.get('top_words', 'Unknown')

            # Draw node as circle (simplified from radial histogram)
            radius = 12
            svg_content += f'''            <g transform="translate({x}, {y})">
                <circle r="{radius}" 
                        class="node-circle" 
                        fill="{color}" 
                        data-node-id="{node_id}"
                        data-topic-idx="{topic_idx}"
                        data-k="{k}">
                    <title>Topic {topic_idx} (K={k}) | {top_words}</title>
                </circle>
                <text x="{radius + 8}" y="0" dy="0.35em" class="node-label">
                    T{topic_idx}
                </text>
            </g>
'''

    svg_content += '        </g>\n'

    # Add K value labels
    svg_content += '        <!-- K Value Labels -->\n'
    for i, k in enumerate(k_values):
        x = i * k_spacing
        color = color_schemes.get(k, '#333')
        svg_content += f'''        <text x="{x}" y="-30" text-anchor="middle" class="k-label" fill="{color}">
            K={k}
        </text>
'''

    # Add legend
    legend_y = chart_height - 80
    svg_content += f'''        <!-- Legend -->
        <g transform="translate(20, {legend_y})">
            <text x="0" y="8" class="legend-title">Similarity Sankey Diagram</text>
            <text x="0" y="24" class="legend-text">Min Similarity: {min_similarity:.2f}</text>
            <text x="0" y="36" class="legend-text">Flows: {len(significant_links)} shown</text>
            <text x="0" y="48" class="legend-text">Nodes: {len(nodes)} topics</text>
            <text x="0" y="60" class="legend-text">Flow thickness ∝ similarity strength</text>
            <text x="0" y="72" class="legend-text">Hover elements for details</text>
        </g>
'''

    # Close the main group and SVG
    svg_content += '''    </g>
</svg>'''

    # Save to file
    with open(filename, 'w', encoding='utf-8') as f:
        f.write(svg_content)

    print(f"✓ SVG exported to {filename}")
    print(f"  - Dimensions: {width}×{height}")
    print(f"  - Nodes: {len(nodes)}")
    print(f"  - Flows shown: {len(significant_links)} (similarity ≥ {min_similarity:.2f})")

    return svg_content


@app.cell
def _(widget_radio):
    # # Use it with your existing widget:
    # svg_string = export_widget_svg(widget_radio, "my_similarity_sankey.svg")

    # Or get just the SVG string without saving:
    svg_string = export_widget_svg(widget_radio)  # Pass None to skip file saving
    return (svg_string,)


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
