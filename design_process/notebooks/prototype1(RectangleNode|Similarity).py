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

    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent.resolve()))
    return (
        Dict,
        List,
        Optional,
        Path,
        Tuple,
        cosine_similarity,
        go,
        mo,
        np,
        pd,
        px,
    )


@app.cell(hide_code=True)
def _(Path, mo):
    import datetime
    import subprocess


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
    return


@app.cell
def _(mo):
    mo.md(r"""## data processing""")
    return


@app.cell
def _(pd):
    metadata_df= pd.read_csv('design_process/data/prototype1/metadata_new_updated.csv', index_col=0)
    features_metadata=metadata_df[["Country", 'Breed_type', 'Outdoor_access', 'Bedding_present', 'Slatted floor', "Age_category"]]
    topic_word_folder = "design_process/data/prototype1/ASVProbabilities"  # Folder with ASVProbabilities files
    sample_topic_folder = "design_process/data/prototype1/SampleProbabilities_wide"
    return features_metadata, sample_topic_folder, topic_word_folder


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
        calculate_topic_similarities,
        extract_topic_evolution_data,
        get_global_ids,
        prepare_sankey_data,
    )


@app.cell(hide_code=True)
def _(
    analyze_sample_reassignments,
    calculate_topic_similarities,
    extract_topic_evolution_data,
    prepare_sankey_data,
):
    def run_topic_evolution_analysis(selected_global_ids, topic_word_folder, sample_topic_folder, embeddings_df=None):
        """
        Complete pipeline for topic evolution analysis.
        """

        print("=== EXTRACTING TOPIC EVOLUTION DATA ===")
        evolution_data = extract_topic_evolution_data(
            selected_global_ids=selected_global_ids,
            topic_word_folder=topic_word_folder,
            sample_topic_folder=sample_topic_folder,
            embeddings_df=embeddings_df
        )

        print("\n=== CALCULATING TOPIC SIMILARITIES ===")
        similarity_df = calculate_topic_similarities(evolution_data, similarity_threshold=0.3)
        print(f"Found {len(similarity_df)} topic relationships")

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
            'reassignment_df': reassignment_df
        }
    return (run_topic_evolution_analysis,)


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
    return


@app.cell
def _(get_global_ids, topic_word_folder):
    global_ids_test = get_global_ids(topic_word_folder)
    return (global_ids_test,)


@app.cell
def _(
    global_ids_test,
    run_topic_evolution_analysis,
    sample_topic_folder,
    topic_word_folder,
):
    results_topic_evolution = run_topic_evolution_analysis(
        selected_global_ids=global_ids_test,
        topic_word_folder=topic_word_folder,
        sample_topic_folder=sample_topic_folder, 
        # embeddings_df=embeddings_df_with_cluster
    )
    return (results_topic_evolution,)


@app.cell(hide_code=True)
def _(Dict, go, np, pd, px):
    def extract_feature_analysis_for_sankey(
        evolution_data: Dict,
        metadata_df: pd.DataFrame, 
        representation_threshold: float = 0.75
    ) -> Dict:
        """
        Extract feature analysis for each topic to use in Sankey hover text.

        Args:
            evolution_data: Output from extract_topic_evolution_data
            metadata_df: DataFrame with sample metadata/features
            representation_threshold: Threshold for considering samples as "most represented"

        Returns:
            Dictionary mapping global_id to feature summary string
        """

        sample_topic_matrix = evolution_data['sample_topic_matrix']
        topic_metadata_df = evolution_data['topic_metadata']

        feature_summaries = {}

        for _, topic_meta in topic_metadata_df.iterrows():
            global_id = topic_meta['global_id']

            # Get topic assignments
            topic_assignments = sample_topic_matrix.loc[global_id]

            # Find highly represented samples
            highly_represented = topic_assignments[topic_assignments >= representation_threshold]

            if len(highly_represented) > 0:
                # Get metadata for highly represented samples
                sample_metadata = metadata_df[metadata_df.index.isin(highly_represented.index)]

                # Analyze features
                feature_analysis = {}

                for column in metadata_df.columns:
                    if sample_metadata[column].dtype == 'object' or sample_metadata[column].dtype.name == 'category':
                        # Categorical feature
                        value_counts = sample_metadata[column].value_counts()
                        if len(value_counts) > 0:
                            most_common = value_counts.iloc[0]
                            most_common_value = value_counts.index[0]
                            percentage = (most_common / len(sample_metadata)) * 100
                            feature_analysis[column] = f"{most_common_value} ({percentage:.1f}%)"

                    elif np.issubdtype(sample_metadata[column].dtype, np.number):
                        # Numerical feature
                        mean_val = sample_metadata[column].mean()
                        std_val = sample_metadata[column].std()
                        feature_analysis[column] = f"{mean_val:.2f} ± {std_val:.2f}"

                # Create summary string
                n_highly_rep = len(highly_represented)
                avg_rep = highly_represented.mean()

                feature_summaries[global_id] = {
                    'n_highly_represented': n_highly_rep,
                    'avg_representation': avg_rep,
                    'feature_analysis': feature_analysis
                }
            else:
                # No highly represented samples
                feature_summaries[global_id] = {
                    'n_highly_represented': 0,
                    'avg_representation': 0,
                    'feature_analysis': {}
                }

        return feature_summaries


    def create_topic_evolution_sankey_with_features(
        sankey_data: Dict,
        evolution_data: Dict,
        metadata_df: pd.DataFrame,
        title: str = "Topic Evolution Across K Values",
        width: int = 1000,
        height: int = 600,
        color_scheme: str = "Set3",
        show_similarity_threshold: float = 0.3,
        min_flow_width: float = 0.1,
        representation_threshold: float = 0.75,
        enable_click_callback: bool = True
    ) -> go.Figure:
        """
        Create an interactive Plotly Sankey diagram with feature analysis in hover text and click callbacks.

        Args:
            sankey_data: Output from prepare_sankey_data function
            evolution_data: Output from extract_topic_evolution_data function
            metadata_df: DataFrame with sample metadata/features
            title: Title for the plot
            width: Plot width in pixels
            height: Plot height in pixels
            color_scheme: Color scheme for nodes
            show_similarity_threshold: Only show links above this similarity
            min_flow_width: Minimum flow width for visibility
            representation_threshold: Threshold for considering samples as "most represented"
            enable_click_callback: Whether to enable click callbacks on links

        Returns:
            Plotly Figure object with click callback data attached
        """

        # Extract feature analysis for all topics
        feature_summaries = extract_feature_analysis_for_sankey(
            evolution_data, metadata_df, representation_threshold
        )

        nodes = sankey_data['nodes']
        links = sankey_data['links']

        # Filter links by similarity threshold
        filtered_links = [link for link in links if link.get('similarity', 1.0) >= show_similarity_threshold]

        # Adjust flow values for better visualization
        flow_values = [max(link['value'], min_flow_width) for link in filtered_links]

        # Create color palette for nodes based on k_value
        k_values = sorted(list(set([node['k_value'] for node in nodes])))
        colors = px.colors.qualitative.Set3[:len(k_values)]
        k_color_map = {k: colors[i % len(colors)] for i, k in enumerate(k_values)}

        # Assign colors to nodes based on k_value
        node_colors = [k_color_map[node['k_value']] for node in nodes]

        # Create node labels with enhanced information
        node_labels = []
        node_hover_text = []

        for node in nodes:
            # Main label
            label = f"K{node['k_value']}-T{node['topic_idx']}"
            node_labels.append(label)

            # Get feature analysis for this topic
            global_id = node['global_id']
            features = feature_summaries.get(global_id, {})

            # Format feature analysis for hover text
            n_highly_rep = features.get('n_highly_represented', 0)
            avg_rep = features.get('avg_representation', 0)
            feature_analysis = features.get('feature_analysis', {})

            if n_highly_rep > 0 and feature_analysis:
                # Format feature analysis - limit to top 5 features for readability
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

            # Enhanced hover text with detailed information
            hover_text = f"""
    <b>{label}</b><br>
    <b>Topic Content:</b><br>
    Top Words: {node['top_words']}<br>
    Sum Probability: {node['sum_probability']:.3f}<br>
    {feature_text}<br>
    Global ID: {node['global_id']}
            """
            node_hover_text.append(hover_text)

        # Create link hover text and callback data
        link_hover_text = []
        link_callback_data = []

        for i, link in enumerate(filtered_links):
            source_node = nodes[link['source']]
            target_node = nodes[link['target']]

            hover_text = f"""
    <b>Topic Evolution</b><br>
    From: K{source_node['k_value']}-T{source_node['topic_idx']}<br>
    To: K{target_node['k_value']}-T{target_node['topic_idx']}<br>
    Similarity: {link['similarity']:.3f}<br>
    Flow Volume: {link['value']:.3f}
            """
            link_hover_text.append(hover_text)

            # Create structured callback data for each link
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

        # Create the Sankey diagram
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
                color = ['rgba(100,100,100,0.3)' for _ in filtered_links],  # Semi-transparent gray
                hovertemplate = '%{customdata}<extra></extra>',
                customdata = link_hover_text
            )
        )])

        # Store callback data in the figure for access during click events
        if enable_click_callback:
            fig._link_callback_data = link_callback_data

            # Add JavaScript callback for click events
            fig.update_layout(
                clickmode='event+select'
            )

        # Update layout
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

        # Add annotations for k-value columns
        k_positions = {}
        for i, node in enumerate(nodes):
            k_val = node['k_value']
            if k_val not in k_positions:
                k_positions[k_val] = []
            k_positions[k_val].append(i)

        # Add k-value labels at the top
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


    # Helper function to handle click events in Marimo
    def handle_sankey_click(plotly_click_data, sankey_figure):
        """
        Handle click events on Sankey diagram links.

        Args:
            plotly_click_data: Click event data from Marimo's plotly widget
            sankey_figure: The Sankey figure object with callback data

        Returns:
            Dictionary with link information or None if no link clicked
        """
        if not plotly_click_data or not hasattr(sankey_figure, '_link_callback_data'):
            return None

        # Extract point index from click data
        points = plotly_click_data.get('points', [])
        if not points:
            return None

        point = points[0]

        # Check if this is a link click (links have 'source' and 'target' properties)
        if 'source' in point and 'target' in point:
            # Find the corresponding link in our callback data
            source_idx = point['source']
            target_idx = point['target']

            # Find matching link in callback data
            for callback_data in sankey_figure._link_callback_data:
                # Get the original link indices from filtered_links
                original_links = sankey_figure.data[0].link
                link_sources = original_links['source']
                link_targets = original_links['target']

                # Find the link index that matches the clicked link
                for i, (src, tgt) in enumerate(zip(link_sources, link_targets)):
                    if src == source_idx and tgt == target_idx:
                        if i < len(sankey_figure._link_callback_data):
                            return sankey_figure._link_callback_data[i]

        return None


    def create_enhanced_sankey_with_stats_and_features(
        results: Dict,
        metadata_df: pd.DataFrame,
        similarity_threshold: float = 0.3,
        representation_threshold: float = 0.75,
        width=1200,
        height=800,
        title_prefix: str = "Topic Evolution"
    ) -> go.Figure:
        """
        Create Sankey diagram with feature analysis and statistics display.
        Args:
            results: Complete results from run_topic_evolution_analysis
            metadata_df: DataFrame with sample metadata/features
            similarity_threshold: Minimum similarity to show connections
            representation_threshold: Threshold for "most represented" samples
            title_prefix: Prefix for the plot title
        Returns:
            Enhanced Plotly Figure
        """
        sankey_data = results['sankey_data']
        similarity_df = results['similarity_df']
        evolution_data = results['evolution_data']
        # Calculate statistics
        total_topics = len(sankey_data['nodes'])
        total_connections = len(similarity_df[similarity_df['similarity'] >= similarity_threshold])
        k_range = f"K{min(evolution_data['k_values'])}-K{max(evolution_data['k_values'])}"
        title = f"{title_prefix}: {total_topics} Topics, {total_connections} Connections ({k_range})"
        # Create the main Sankey with features
        fig = create_topic_evolution_sankey_with_features(
            sankey_data=sankey_data,
            evolution_data=evolution_data,
            metadata_df=metadata_df,
            title=title,
            show_similarity_threshold=similarity_threshold,
            representation_threshold=representation_threshold
        )
        # Add statistics text box
        stats_text = f"""
    <b>Analysis Statistics:</b><br>
    • Total Topics: {total_topics}<br>
    • Connections: {total_connections}<br>
    • K Values: {k_range}<br>
    • Min Similarity: {similarity_threshold:.2f}<br>
    • Avg Flow: {similarity_df['flow_volume'].mean():.3f}
        """
        fig.add_annotation(
            x = 0.02,
            y = 0.98,
            text = stats_text,
            showarrow = False,
            xref = "paper",
            yref = "paper",
            bgcolor = "lightgray",
            bordercolor = "black",
            borderwidth = 1,
            font = dict(size=10),
            align = "left",
            valign = "top"
        )
        return fig
    return (
        create_enhanced_sankey_with_stats_and_features,
        extract_feature_analysis_for_sankey,
    )


@app.cell(hide_code=True)
def _(create_enhanced_sankey_with_stats_and_features):
    def create_final_sankey_plot(results, metadata_df, similarity_threshold=0.75, representation_threshold=0.75, width=1200,height=800):
        """
        Simple wrapper to create the final Sankey plot with features
        """

        # Filter metadata to match samples in the analysis
        used_samples = results['evolution_data']['sample_topic_matrix'].columns.tolist()
        filtered_metadata = metadata_df[metadata_df.index.isin(used_samples)]

        # Create the enhanced Sankey
        fig = create_enhanced_sankey_with_stats_and_features(
            results=results,
            metadata_df=filtered_metadata,
            similarity_threshold=similarity_threshold,
            representation_threshold=representation_threshold,
            width=width,
            height=height
        )

        return fig
    return (create_final_sankey_plot,)


@app.cell
def _(mo):
    mo.md(r"""## plot""")
    return


@app.cell
def _(
    create_final_sankey_plot,
    features_metadata,
    mo,
    results_topic_evolution,
):
    fig_1 = create_final_sankey_plot(results_topic_evolution, features_metadata, similarity_threshold=0.3, representation_threshold=0.75)
    sankey_widget_1 = mo.ui.plotly(fig_1)
    return (fig_1,)


@app.cell
def _(fig_1):
    fig_1
    return


if __name__ == "__main__":
    app.run()
