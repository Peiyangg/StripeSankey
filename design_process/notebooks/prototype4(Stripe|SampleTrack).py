import marimo

__generated_with = "0.14.10"
app = marimo.App(width="full")


@app.cell
def _():
    import marimo as mo
    import anywidget
    import traitlets

    import pandas as pd
    import matplotlib.pyplot as plt
    import seaborn as sns
    import numpy as np
    from scipy import stats
    from sklearn.preprocessing import StandardScaler

    import os
    from collections import defaultdict
    import json

    from sklearn.discriminant_analysis import LinearDiscriminantAnalysis
    from scipy.stats import wilcoxon, kruskal
    from itertools import combinations
    import warnings

    from glob import glob
    import re
    import xml.etree.ElementTree as ET


    # from skbio.stats.composition import ancom, dirmult_ttest, multiplicative_replacement
    warnings.filterwarnings('ignore')
    return (
        ET,
        anywidget,
        defaultdict,
        glob,
        json,
        mo,
        np,
        os,
        pd,
        re,
        traitlets,
    )


@app.cell
def _(mo):
    mo.md(r"""## Data processing""")
    return


@app.cell
def _(pd):
    metadata_df= pd.read_csv('data/prototype1/metadata_new_updated.csv', index_col=0)
    features_metadata=metadata_df[["Country", 'Breed_type', 'Outdoor_access', 'Bedding_present', 'Slatted floor', "Age_category"]]

    MC_feature_folder_path = "data/prototype1/ASVProbabilities" 
    Sample_MC_folder_path = "data/prototype1/SampleProbabilities_wide"


    return MC_feature_folder_path, Sample_MC_folder_path


@app.cell(hide_code=True)
def _(ET, defaultdict, glob, json, np, os, pd, re):
    class StripeSankeyDataProcessor:
        def __init__(self, sample_mc_folder, mc_feature_folder):
            self.sample_mc_folder = sample_mc_folder
            self.mc_feature_folder = mc_feature_folder
            self.k_range = range(2, 11)  # K from 2 to 10

            # Thresholds for representation levels
            self.high_threshold = 0.67
            self.medium_threshold = 0.33

        def load_sample_mc_data(self):
            """Load all sample-MC probability files"""
            sample_mc_data = {}

            for k in self.k_range:
                filename = f'DirichletComponentProbabilities_{k}.csv'
                filepath = os.path.join(self.sample_mc_folder, filename)

                if os.path.exists(filepath):
                    df = pd.read_csv(filepath, index_col=0)  # First column is MC names, rows=MCs, cols=samples
                    sample_mc_data[k] = df
                    print(f"Loaded K={k}: {df.shape[0]} topics (MCs), {df.shape[1]} samples")

                    # Sanity check - K=k should have exactly k topics (rows)
                    if df.shape[0] != k:
                        print(f"WARNING: K={k} has {df.shape[0]} topics, expected {k}")
                else:
                    print(f"File not found: {filename}")

            return sample_mc_data

        def categorize_sample_assignments(self, sample_mc_data):
            """
            For each topic at each K, categorize samples into high/medium representation levels
            Data structure: rows=MCs, columns=samples
            """
            categorized_data = {}

            for k, df in sample_mc_data.items():
                k_data = {
                    'nodes': {},  # topic_id -> {high_samples: [], medium_samples: [], high_count: int, medium_count: int, total_prob: float}
                    'sample_assignments': {}  # sample_id -> {assigned_topic: str, probability: float, level: str}
                }

                # Process each topic (row in the DataFrame)
                for topic_idx in range(df.shape[0]):
                    topic_name = f"K{k}_MC{topic_idx}"

                    # Get all sample probabilities for this topic (row across all samples)
                    topic_probs = df.iloc[topic_idx, :]  # This topic's probabilities across all samples

                    # Categorize samples by their probability for this topic
                    high_samples = []
                    medium_samples = []
                    total_prob = 0

                    for sample_name, prob in topic_probs.items():
                        if prob >= self.high_threshold:
                            high_samples.append((sample_name, prob))
                            total_prob += prob
                        elif prob >= self.medium_threshold:
                            medium_samples.append((sample_name, prob))
                            total_prob += prob

                    k_data['nodes'][topic_name] = {
                        'high_samples': high_samples,
                        'medium_samples': medium_samples,
                        'high_count': len(high_samples),
                        'medium_count': len(medium_samples),
                        'total_probability': total_prob
                    }

                # For each sample, find its PRIMARY topic assignment (highest probability above threshold)
                for sample_idx, sample_name in enumerate(df.columns):
                    sample_column = df.iloc[:, sample_idx]  # All topic probabilities for this sample

                    # Find the topic with highest probability above minimum threshold
                    max_prob = 0
                    assigned_topic = None
                    assignment_level = None

                    for topic_idx, prob in enumerate(sample_column):
                        if prob >= self.medium_threshold and prob > max_prob:
                            max_prob = prob
                            assigned_topic = f"K{k}_MC{topic_idx}"
                            assignment_level = 'high' if prob >= self.high_threshold else 'medium'

                    if assigned_topic:
                        k_data['sample_assignments'][sample_name] = {
                            'assigned_topic': assigned_topic,
                            'probability': max_prob,
                            'level': assignment_level
                        }

                categorized_data[k] = k_data
                print(f"K={k}: {len(k_data['sample_assignments'])} samples assigned to topics")

            return categorized_data

        def calculate_flows(self, categorized_data):
            """Calculate flows between consecutive K values based on sample reassignments"""
            flows = []

            k_values = sorted(categorized_data.keys())

            for i in range(len(k_values) - 1):
                source_k = k_values[i]
                target_k = k_values[i + 1]

                source_assignments = categorized_data[source_k]['sample_assignments']
                target_assignments = categorized_data[target_k]['sample_assignments']

                # Track flows between specific segments (topic + level combinations)
                flow_counts = defaultdict(lambda: defaultdict(int))
                flow_samples = defaultdict(lambda: defaultdict(list))

                # Find samples that have assignments in both K values
                common_samples = set(source_assignments.keys()) & set(target_assignments.keys())
                print(f"K{source_k}→K{target_k}: {len(common_samples)} samples to track")

                for sample in common_samples:
                    source_info = source_assignments[sample]
                    target_info = target_assignments[sample]

                    # Create segment identifiers (topic + representation level)
                    source_segment = f"{source_info['assigned_topic']}_{source_info['level']}"
                    target_segment = f"{target_info['assigned_topic']}_{target_info['level']}"

                    flow_counts[source_segment][target_segment] += 1
                    flow_samples[source_segment][target_segment].append({
                        'sample': sample,
                        'source_prob': source_info['probability'],
                        'target_prob': target_info['probability']
                    })

                # Convert to flow records
                for source_segment, targets in flow_counts.items():
                    for target_segment, count in targets.items():
                        if count > 0:  # Only include actual flows
                            avg_prob = np.mean([
                                (s['source_prob'] + s['target_prob']) / 2 
                                for s in flow_samples[source_segment][target_segment]
                            ])

                            flows.append({
                                'source_k': source_k,
                                'target_k': target_k,
                                'source_segment': source_segment,
                                'target_segment': target_segment,
                                'sample_count': count,
                                'average_probability': avg_prob,
                                'samples': flow_samples[source_segment][target_segment]
                            })

            print(f"Total flows calculated: {len(flows)}")
            return flows

        def prepare_sankey_data(self):
            """Main function to prepare all data for Sankey diagram"""
            print("Loading sample-MC data...")
            sample_mc_data = self.load_sample_mc_data()

            if not sample_mc_data:
                print("❌ No data loaded. Check your file paths and naming.")
                return None, None

            print("\nCategorizing sample assignments...")
            categorized_data = self.categorize_sample_assignments(sample_mc_data)

            print("\nCalculating flows...")
            flows = self.calculate_flows(categorized_data)

            # Prepare final data structure for StripeSankey
            sankey_data = {
                'nodes': {},
                'flows': flows,
                'k_range': list(sample_mc_data.keys()),  # Only include K values we actually have
                'thresholds': {
                    'high': self.high_threshold,
                    'medium': self.medium_threshold
                },
                'metadata': {
                    'total_samples': sample_mc_data[list(sample_mc_data.keys())[0]].shape[1] if sample_mc_data else 0,  # columns = samples
                    'k_values_processed': list(sample_mc_data.keys())
                }
            }

            # Collect all node data
            for k, k_data in categorized_data.items():
                for topic_name, node_data in k_data['nodes'].items():
                    sankey_data['nodes'][topic_name] = node_data

            print(f"\n✅ Data processing complete!")
            print(f"📊 Summary:")
            print(f"   - K values: {sankey_data['k_range']}")
            print(f"   - Total nodes: {len(sankey_data['nodes'])}")
            print(f"   - Total flows: {len(flows)}")
            print(f"   - Samples tracked: {sankey_data['metadata']['total_samples']}")

            # Show node summary by K
            for k in sankey_data['k_range']:
                k_nodes = [name for name in sankey_data['nodes'].keys() if name.startswith(f'K{k}_')]
                total_assigned = sum(data['high_count'] + data['medium_count'] 
                                   for name, data in sankey_data['nodes'].items() 
                                   if name.startswith(f'K{k}_'))
                print(f"   - K={k}: {len(k_nodes)} topics, {total_assigned} total sample assignments")

            return sankey_data, categorized_data

        def save_processed_data(self, sankey_data, output_path='sankey_data.json'):
            """Save processed data to JSON file"""
            if sankey_data is None:
                print("❌ No data to save")
                return

            # Convert numpy types to native Python types for JSON serialization
            def convert_numpy(obj):
                if isinstance(obj, np.integer):
                    return int(obj)
                elif isinstance(obj, np.floating):
                    return float(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                return obj

            def deep_convert(data):
                if isinstance(data, dict):
                    return {k: deep_convert(v) for k, v in data.items()}
                elif isinstance(data, list):
                    return [deep_convert(item) for item in data]
                else:
                    return convert_numpy(data)

            converted_data = deep_convert(sankey_data)

            with open(output_path, 'w') as f:
                json.dump(converted_data, f, indent=2)

            print(f"💾 Data saved to {output_path}")



        def get_high_representation_samples(self, topic_id, categorized_data=None):
            """
            Get sample IDs that have high representation (>0.67) for a specific topic

            Args:
                topic_id (str): Global topic ID in format 'K{k}_MC{topic_idx}' (e.g., 'K4_MC2')
                categorized_data (dict, optional): Pre-computed categorized data. If None, will process data first.

            Returns:
                dict: {
                    'topic_id': str,
                    'high_samples': list of sample IDs,
                    'high_count': int,
                    'sample_details': list of tuples (sample_id, probability)
                }
            """
            # If categorized_data not provided, process the data first
            if categorized_data is None:
                print("Processing data to get categorized assignments...")
                sample_mc_data = self.load_sample_mc_data()
                if not sample_mc_data:
                    print("❌ No data could be loaded")
                    return None
                categorized_data = self.categorize_sample_assignments(sample_mc_data)

            # Parse the topic_id to extract K value and topic index
            try:
                # Expected format: K{k}_MC{topic_idx}
                parts = topic_id.split('_')
                if len(parts) != 2 or not parts[0].startswith('K') or not parts[1].startswith('MC'):
                    raise ValueError(f"Invalid topic_id format. Expected 'K{{k}}_MC{{topic_idx}}', got '{topic_id}'")

                k_value = int(parts[0][1:])  # Remove 'K' and convert to int
                topic_idx = int(parts[1][2:])  # Remove 'MC' and convert to int

            except (ValueError, IndexError) as e:
                print(f"❌ Error parsing topic_id '{topic_id}': {e}")
                return None

            # Check if K value exists in our data
            if k_value not in categorized_data:
                print(f"❌ K value {k_value} not found in data. Available K values: {list(categorized_data.keys())}")
                return None

            # Check if topic exists in the K value data
            if topic_id not in categorized_data[k_value]['nodes']:
                available_topics = [name for name in categorized_data[k_value]['nodes'].keys() 
                                  if name.startswith(f'K{k_value}_')]
                print(f"❌ Topic '{topic_id}' not found. Available topics for K={k_value}: {available_topics}")
                return None

            # Get the topic data
            topic_data = categorized_data[k_value]['nodes'][topic_id]

            # Extract high representation samples
            high_samples_list = topic_data['high_samples']  # List of tuples (sample_id, probability)
            high_sample_ids = [sample_id for sample_id, prob in high_samples_list]

            result = {
                'topic_id': topic_id,
                'k_value': k_value,
                'topic_index': topic_idx,
                'high_samples': high_sample_ids,
                'high_count': len(high_sample_ids),
                'sample_details': high_samples_list,
                'threshold_used': self.high_threshold
            }

            print(f"✅ Found {len(high_sample_ids)} samples with high representation (>{self.high_threshold}) for topic '{topic_id}'")

            return result


        def extract_topic_coherence(self, xml_file_path):
            """Extract topic coherence data from a single MALLET diagnostic XML file"""
            try:
                # Parse the XML file
                tree = ET.parse(xml_file_path)
                root = tree.getroot()

                # List to store topic data
                topics_data = []

                # Extract data for each topic
                for topic in root.findall('topic'):
                    # Debug: print what we're getting from XML
                    topic_id_raw = topic.get('id')
                    print(f"Debug: Found topic with id='{topic_id_raw}'")

                    try:
                        topic_data = {
                            'topic_id': int(topic.get('id')),
                            'tokens': float(topic.get('tokens')) if topic.get('tokens') else 0.0,
                            'document_entropy': float(topic.get('document_entropy')) if topic.get('document_entropy') else 0.0,
                            'word_length': float(topic.get('word-length')) if topic.get('word-length') else 0.0,
                            'coherence': float(topic.get('coherence')) if topic.get('coherence') else 0.0,
                            'uniform_dist': float(topic.get('uniform_dist')) if topic.get('uniform_dist') else 0.0,
                            'corpus_dist': float(topic.get('corpus_dist')) if topic.get('corpus_dist') else 0.0,
                            'eff_num_words': float(topic.get('eff_num_words')) if topic.get('eff_num_words') else 0.0,
                            'token_doc_diff': float(topic.get('token-doc-diff')) if topic.get('token-doc-diff') else 0.0,
                            'rank_1_docs': float(topic.get('rank_1_docs')) if topic.get('rank_1_docs') else 0.0,
                            'allocation_ratio': float(topic.get('allocation_ratio')) if topic.get('allocation_ratio') else 0.0,
                            'allocation_count': float(topic.get('allocation_count')) if topic.get('allocation_count') else 0.0,
                            'exclusivity': float(topic.get('exclusivity')) if topic.get('exclusivity') else 0.0
                        }
                        topics_data.append(topic_data)

                    except (ValueError, TypeError) as e:
                        print(f"Warning: Could not parse topic {topic_id_raw}: {e}")
                        continue

                # Create DataFrame
                df = pd.DataFrame(topics_data)
                print(f"Extracted {len(df)} topics from {xml_file_path}")
                if not df.empty:
                    print(f"Topic IDs range: {df['topic_id'].min()} to {df['topic_id'].max()}")

                return df

            except ET.ParseError as e:
                print(f"❌ XML parsing error in {xml_file_path}: {e}")
                return pd.DataFrame()
            except Exception as e:
                print(f"❌ Unexpected error processing {xml_file_path}: {e}")
                return pd.DataFrame()

        def load_all_mallet_diagnostics_fixed(self, mallet_folder_path):
            """
            Load all MALLET diagnostic files from a folder and create global topic IDs
            Fixed version with better error handling and debugging

            Args:
                mallet_folder_path (str): Path to folder containing MALLET diagnostic XML files
                                         Files should be named like 'mallet.diagnostics.10.xml'

            Returns:
                pd.DataFrame: Combined dataframe with all topics and global IDs
            """
            # Find all MALLET diagnostic files
            pattern = os.path.join(mallet_folder_path, 'mallet.diagnostics.*.xml')
            xml_files = glob(pattern)

            if not xml_files:
                print(f"❌ No MALLET diagnostic files found in {mallet_folder_path}")
                print(f"Expected pattern: mallet.diagnostics.{{k}}.xml")
                return pd.DataFrame()

            print(f"Found {len(xml_files)} MALLET diagnostic files")

            all_topics_data = []

            for xml_file in sorted(xml_files):
                # Extract K value from filename
                filename = os.path.basename(xml_file)
                k_match = re.search(r'mallet\.diagnostics\.(\d+)\.xml', filename)

                if not k_match:
                    print(f"⚠️ Warning: Could not extract K value from filename {filename}")
                    continue

                k_value = int(k_match.group(1))
                print(f"\nProcessing {filename} -> K={k_value}")

                # Load topic data for this K value
                topics_df = self.extract_topic_coherence(xml_file)

                if topics_df.empty:
                    print(f"❌ No valid topics extracted from {filename}")
                    continue

                # Add K value and create global topic ID using the same logic as Sankey
                topics_df['k_value'] = k_value
                topics_df['global_topic_id'] = topics_df.apply(
                    lambda row: f"K{k_value}_MC{int(row['topic_id'])}", axis=1
                )

                # Add source filename for reference
                topics_df['source_file'] = filename

                all_topics_data.append(topics_df)

                # Show what global IDs we created
                sample_ids = topics_df['global_topic_id'].head(3).tolist()
                print(f"✅ Loaded K={k_value}: {len(topics_df)} topics")
                print(f"   Sample global IDs: {sample_ids}")

            if not all_topics_data:
                print("❌ No valid data could be loaded from any files")
                return pd.DataFrame()

            # Combine all data
            combined_df = pd.concat(all_topics_data, ignore_index=True)

            # Reorder columns to put global_topic_id first
            cols = ['global_topic_id', 'k_value', 'topic_id'] + [col for col in combined_df.columns 
                                                                  if col not in ['global_topic_id', 'k_value', 'topic_id']]
            combined_df = combined_df[cols]

            print(f"\n✅ Combined MALLET diagnostics loaded successfully!")
            print(f"📊 Total topics: {len(combined_df)}")
            print(f"📊 K values: {sorted(combined_df['k_value'].unique())}")

            # Show sample of final global IDs
            sample_global_ids = combined_df['global_topic_id'].head(10).tolist()
            print(f"📊 Sample global IDs: {sample_global_ids}")

            return combined_df

        def integrate_mallet_diagnostics_fixed(self, sankey_data, mallet_folder_path):
            """
            Fixed version of MALLET integration with better debugging
            """
            print("🔧 Using FIXED MALLET integration...")

            # Load MALLET diagnostics using the fixed function
            mallet_df = self.load_all_mallet_diagnostics_fixed(mallet_folder_path)

            if mallet_df.empty:
                print("❌ No MALLET data to integrate")
                return sankey_data

            print(f"\n🔍 INTEGRATION DEBUG:")
            print(f"Sankey topics (first 5): {list(sankey_data['nodes'].keys())[:5]}")
            print(f"MALLET topics (first 5): {mallet_df['global_topic_id'].head().tolist()}")

            # Create a dictionary for fast lookup
            mallet_dict = mallet_df.set_index('global_topic_id').to_dict('index')

            # Track integration statistics
            integrated_count = 0
            missing_count = 0
            missing_topics = []

            # Integrate MALLET data into existing sankey nodes
            for topic_id, node_data in sankey_data['nodes'].items():
                if topic_id in mallet_dict:
                    # Add all MALLET diagnostic metrics to the node
                    mallet_data = mallet_dict[topic_id]

                    # Add MALLET metrics to node data
                    node_data['mallet_diagnostics'] = {
                        'coherence': mallet_data['coherence'],
                        'tokens': mallet_data['tokens'],
                        'document_entropy': mallet_data['document_entropy'],
                        'word_length': mallet_data['word_length'],
                        'uniform_dist': mallet_data['uniform_dist'],
                        'corpus_dist': mallet_data['corpus_dist'],
                        'eff_num_words': mallet_data['eff_num_words'],
                        'token_doc_diff': mallet_data['token_doc_diff'],
                        'rank_1_docs': mallet_data['rank_1_docs'],
                        'allocation_ratio': mallet_data['allocation_ratio'],
                        'allocation_count': mallet_data['allocation_count'],
                        'exclusivity': mallet_data['exclusivity']
                    }

                    integrated_count += 1
                else:
                    missing_count += 1
                    missing_topics.append(topic_id)

            # Update metadata
            sankey_data['metadata']['mallet_integration'] = {
                'integrated_topics': integrated_count,
                'missing_topics': missing_count,
                'total_mallet_topics': len(mallet_df),
                'integration_date': pd.Timestamp.now().isoformat(),
                'mallet_folder': mallet_folder_path
            }

            print(f"\n✅ MALLET integration complete!")
            print(f"📊 Integration summary:")
            print(f"   - Topics with MALLET data: {integrated_count}")
            print(f"   - Topics missing MALLET data: {missing_count}")
            print(f"   - Total MALLET topics available: {len(mallet_df)}")

            if missing_topics and len(missing_topics) <= 10:
                print(f"   - Missing topics: {missing_topics}")
            elif missing_topics:
                print(f"   - Missing topics (first 10): {missing_topics[:10]}...")

            # If still no matches, show some debugging info
            if integrated_count == 0:
                print("\n🔍 NO MATCHES FOUND - DEBUG INFO:")
                print("Available MALLET topic IDs:")
                for topic_id in sorted(mallet_dict.keys())[:10]:
                    print(f"   '{topic_id}'")
                print("\nAvailable Sankey topic IDs:")
                for topic_id in sorted(sankey_data['nodes'].keys())[:10]:
                    print(f"   '{topic_id}'")

            return sankey_data


        def load_perplexity_data(self, csv_file_path):
            """
            Load perplexity data from CSV file

            Args:
                csv_file_path (str): Path to CSV file containing Num_MCs and Perplexity columns

            Returns:
                dict: Dictionary mapping K values to perplexity scores
            """
            try:
                # Load the CSV file
                df = pd.read_csv(csv_file_path)

                # Clean up column names (remove any unnamed columns)
                df = df.loc[:, ~df.columns.str.contains('^Unnamed')]

                print(f"📊 Loaded perplexity data from {csv_file_path}")
                print(f"   Columns: {list(df.columns)}")
                print(f"   Rows: {len(df)}")

                # Check required columns
                if 'Num_MCs' not in df.columns:
                    print("❌ 'Num_MCs' column not found in CSV")
                    return {}

                if 'Perplexity' not in df.columns:
                    print("❌ 'Perplexity' column not found in CSV")
                    return {}

                # Create dictionary mapping K values to perplexity scores
                perplexity_dict = {}

                for _, row in df.iterrows():
                    k_value = int(row['Num_MCs'])
                    perplexity = float(row['Perplexity'])
                    perplexity_dict[k_value] = perplexity

                print(f"✅ Loaded perplexity data for K values: {sorted(perplexity_dict.keys())}")
                print(f"   Sample data: K=2 -> {perplexity_dict.get(2, 'N/A'):.4f}")

                return perplexity_dict

            except Exception as e:
                print(f"❌ Error loading perplexity data: {e}")
                return {}

        def integrate_perplexity_data(self, sankey_data, csv_file_path):
            """
            Integrate perplexity data with existing Sankey data
            All topics under the same K value get the same perplexity score

            Args:
                sankey_data (dict): Existing sankey data structure
                csv_file_path (str): Path to CSV file with perplexity data

            Returns:
                dict: Updated sankey_data with perplexity information
            """
            # Load perplexity data
            perplexity_dict = self.load_perplexity_data(csv_file_path)

            if not perplexity_dict:
                print("❌ No perplexity data to integrate")
                return sankey_data

            # Track integration statistics
            integrated_count = 0
            missing_count = 0
            k_values_found = set()
            k_values_missing = set()

            # Integrate perplexity data into existing sankey nodes
            for topic_id, node_data in sankey_data['nodes'].items():
                # Extract K value from topic_id (format: K{k}_MC{topic_idx})
                try:
                    k_part = topic_id.split('_')[0]
                    if k_part.startswith('K'):
                        k_value = int(k_part[1:])

                        if k_value in perplexity_dict:
                            # Add perplexity data to node
                            if 'model_metrics' not in node_data:
                                node_data['model_metrics'] = {}

                            node_data['model_metrics']['perplexity'] = perplexity_dict[k_value]
                            node_data['model_metrics']['k_value'] = k_value

                            integrated_count += 1
                            k_values_found.add(k_value)
                        else:
                            missing_count += 1
                            k_values_missing.add(k_value)

                except (ValueError, IndexError) as e:
                    print(f"⚠️ Warning: Could not parse K value from topic_id '{topic_id}': {e}")
                    missing_count += 1

            # Update metadata
            if 'model_integration' not in sankey_data['metadata']:
                sankey_data['metadata']['model_integration'] = {}

            sankey_data['metadata']['model_integration']['perplexity'] = {
                'integrated_topics': integrated_count,
                'missing_topics': missing_count,
                'k_values_with_perplexity': sorted(k_values_found),
                'k_values_missing_perplexity': sorted(k_values_missing),
                'total_k_values_available': len(perplexity_dict),
                'integration_date': pd.Timestamp.now().isoformat(),
                'source_file': csv_file_path
            }

            print(f"\n✅ Perplexity integration complete!")
            print(f"📊 Integration summary:")
            print(f"   - Topics with perplexity data: {integrated_count}")
            print(f"   - Topics missing perplexity data: {missing_count}")
            print(f"   - K values with perplexity: {sorted(k_values_found)}")

            if k_values_missing:
                print(f"   - K values missing perplexity: {sorted(k_values_missing)}")

            return sankey_data

        def integrate_all_model_data(self, sankey_data, mallet_folder_path, perplexity_csv_path):
            """
            Comprehensive function to integrate both MALLET diagnostics and perplexity data

            Args:
                sankey_data (dict): Existing sankey data structure
                mallet_folder_path (str): Path to folder containing MALLET diagnostic files
                perplexity_csv_path (str): Path to CSV file with perplexity data

            Returns:
                dict: Updated sankey_data with all model metrics integrated
            """
            print("🔧 Integrating all model data...")
            print("=" * 50)

            # First integrate MALLET diagnostics
            print("1️⃣ Integrating MALLET diagnostics...")
            sankey_data = self.integrate_mallet_diagnostics_fixed(sankey_data, mallet_folder_path)

            # Then integrate perplexity data
            print("\n2️⃣ Integrating perplexity data...")
            sankey_data = self.integrate_perplexity_data(sankey_data, perplexity_csv_path)

            print("\n✅ All model data integration complete!")

            # Show summary of what's available for a sample topic
            sample_topic = list(sankey_data['nodes'].keys())[0]
            sample_node = sankey_data['nodes'][sample_topic]

            print(f"\n📊 Sample topic '{sample_topic}' now contains:")
            print(f"   - Sample data: high_count={sample_node.get('high_count', 0)}, medium_count={sample_node.get('medium_count', 0)}")

            if 'mallet_diagnostics' in sample_node:
                mallet_data = sample_node['mallet_diagnostics']
                print(f"   - MALLET data: coherence={mallet_data.get('coherence', 'N/A'):.4f}, exclusivity={mallet_data.get('exclusivity', 'N/A'):.4f}")
            else:
                print("   - MALLET data: Not available")

            if 'model_metrics' in sample_node:
                model_data = sample_node['model_metrics']
                print(f"   - Model data: perplexity={model_data.get('perplexity', 'N/A'):.4f}")
            else:
                print("   - Model data: Not available")

            return sankey_data

        def get_topic_all_metrics(self, topic_id, sankey_data):
            """
            Get all available metrics for a specific topic (samples, MALLET, perplexity)

            Args:
                topic_id (str): Global topic ID (e.g., 'K4_MC2')
                sankey_data (dict): Sankey data with integrated metrics

            Returns:
                dict: All available metrics for the topic
            """
            if topic_id not in sankey_data['nodes']:
                print(f"❌ Topic '{topic_id}' not found in sankey data")
                return None

            node_data = sankey_data['nodes'][topic_id]

            # Compile all metrics
            all_metrics = {
                'topic_id': topic_id,
                'sample_metrics': {
                    'high_count': node_data.get('high_count', 0),
                    'medium_count': node_data.get('medium_count', 0),
                    'total_probability': node_data.get('total_probability', 0),
                    'high_samples': [sample_id for sample_id, prob in node_data.get('high_samples', [])],
                    'medium_samples': [sample_id for sample_id, prob in node_data.get('medium_samples', [])]
                }
            }

            # Add MALLET diagnostics if available
            if 'mallet_diagnostics' in node_data:
                all_metrics['mallet_diagnostics'] = node_data['mallet_diagnostics']

            # Add model metrics if available
            if 'model_metrics' in node_data:
                all_metrics['model_metrics'] = node_data['model_metrics']

            return all_metrics

        def export_comprehensive_topic_summary(self, sankey_data, output_path='topic_comprehensive_summary.csv'):
            """
            Export a comprehensive CSV with all metrics for all topics

            Args:
                sankey_data (dict): Sankey data with all integrated metrics
                output_path (str): Path for output CSV file

            Returns:
                pd.DataFrame: Summary dataframe
            """
            summary_data = []

            for topic_id, node_data in sankey_data['nodes'].items():
                # Parse topic info
                try:
                    parts = topic_id.split('_')
                    k_value = int(parts[0][1:])  # Remove 'K'
                    topic_idx = int(parts[1][2:])  # Remove 'MC'
                except:
                    k_value = None
                    topic_idx = None

                # Base metrics
                row = {
                    'topic_id': topic_id,
                    'k_value': k_value,
                    'topic_index': topic_idx,
                    'high_count': node_data.get('high_count', 0),
                    'medium_count': node_data.get('medium_count', 0),
                    'total_probability': node_data.get('total_probability', 0)
                }

                # Add MALLET diagnostics
                if 'mallet_diagnostics' in node_data:
                    mallet_data = node_data['mallet_diagnostics']
                    for key, value in mallet_data.items():
                        row[f'mallet_{key}'] = value

                # Add model metrics
                if 'model_metrics' in node_data:
                    model_data = node_data['model_metrics']
                    for key, value in model_data.items():
                        row[f'model_{key}'] = value

                summary_data.append(row)

            # Create DataFrame
            summary_df = pd.DataFrame(summary_data)

            # Sort by K value and topic index
            if 'k_value' in summary_df.columns and 'topic_index' in summary_df.columns:
                summary_df = summary_df.sort_values(['k_value', 'topic_index'])

            # Save to CSV
            summary_df.to_csv(output_path, index=False)

            print(f"✅ Comprehensive topic summary exported to {output_path}")
            print(f"📊 Summary: {len(summary_df)} topics with {len(summary_df.columns)} metrics each")

            return summary_df
    return (StripeSankeyDataProcessor,)


@app.cell
def _(
    MC_feature_folder_path,
    Sample_MC_folder_path,
    StripeSankeyDataProcessor,
):
    if __name__ == "__main__":
        # Set your folder paths
        MC_feature_folder = MC_feature_folder_path  # Replace with actual path
        Sample_MC_folder = Sample_MC_folder_path     # Replace with actual path

        # Initialize processor
        processor = StripeSankeyDataProcessor(Sample_MC_folder, MC_feature_folder)

        # Process data
        sankey_data, raw_categorized = processor.prepare_sankey_data()

        # Save processed data
        processor.save_processed_data(sankey_data)

        mallet_folder = '/Users/huopeiyang/Library/CloudStorage/OneDrive-KULeuven/py_working/LDA_workflow/VIZ_design/9Models_Luke/Diagnosis'
        preplexity_path = '/Users/huopeiyang/Library/CloudStorage/OneDrive-KULeuven/py_working/Luke_data/Luke_WP1/lda_asv/lda_loop/all_MC_metrics_2_20.csv'
        updated_sankey_data = processor.integrate_mallet_diagnostics_fixed(sankey_data, mallet_folder)

        fully_integrated_data = processor.integrate_all_model_data(
        sankey_data, 
        mallet_folder, 
        preplexity_path
    )
    return (fully_integrated_data,)


@app.cell(hide_code=True)
def _(anywidget, traitlets):
    class StripeSankeyInline(anywidget.AnyWidget):
        _esm = """
        import * as d3 from "https://cdn.skypack.dev/d3@7";

        function render({ model, el }) {
            el.innerHTML = '';

            const data = model.get("sankey_data");
            const width = model.get("width");
            const height = model.get("height");
            const colorSchemes = model.get("color_schemes");
            const selectedFlow = model.get("selected_flow");
            const metricMode = model.get("metric_mode");
            const metricConfig = model.get("metric_config");

            if (!data || !data.nodes || Object.keys(data.nodes).length === 0) {
                el.innerHTML = '<div style="padding: 20px; text-align: center; font-family: sans-serif;">No data available. Please load your processed data first.</div>';
                return;
            }

            // Create SVG
            const svg = d3.select(el)
                .append("svg")
                .attr("width", width)
                .attr("height", height)
                .style("background", "#fafafa")
                .style("border", "1px solid #ddd");

            const margin = { top: 60, right: 150, bottom: 60, left: 100 }; // Increased right margin for tooltips
            const chartWidth = width - margin.left - margin.right;
            const chartHeight = height - margin.top - margin.bottom;

            const g = svg.append("g")
                .attr("transform", `translate(${margin.left}, ${margin.top})`);

            // Process data for visualization
            const processedData = processDataForVisualization(data);

            // Calculate metric scales if in metric mode
            let metricScales = null;
            if (metricMode) {
                metricScales = calculateMetricScales(processedData, data, metricConfig);
            }

            // Draw the actual sankey diagram
            drawSankeyDiagram(g, processedData, chartWidth, chartHeight, colorSchemes, selectedFlow, model, metricMode, metricScales, metricConfig);

            // No metric legend - removed to avoid clutter

            // Update on data change
            model.on("change:sankey_data", () => {
                const newData = model.get("sankey_data");
                if (newData && Object.keys(newData).length > 0) {
                    const newProcessedData = processDataForVisualization(newData);
                    let newMetricScales = null;
                    if (model.get("metric_mode")) {
                        newMetricScales = calculateMetricScales(newProcessedData, newData, model.get("metric_config"));
                    }
                    svg.selectAll("*").remove();
                    const newG = svg.append("g").attr("transform", `translate(${margin.left}, ${margin.top})`);
                    drawSankeyDiagram(newG, newProcessedData, chartWidth, chartHeight, colorSchemes, model.get("selected_flow"), model, model.get("metric_mode"), newMetricScales, model.get("metric_config"));
                    // No metric legend - removed
                }
            });

            // Update on metric mode change
            model.on("change:metric_mode", () => {
                const newMetricMode = model.get("metric_mode");
                let newMetricScales = null;
                if (newMetricMode) {
                    newMetricScales = calculateMetricScales(processedData, data, model.get("metric_config"));
                }
                svg.selectAll("*").remove();
                const newG = svg.append("g").attr("transform", `translate(${margin.left}, ${margin.top})`);
                drawSankeyDiagram(newG, processedData, chartWidth, chartHeight, colorSchemes, model.get("selected_flow"), model, newMetricMode, newMetricScales, model.get("metric_config"));
                // No metric legend - removed
            });

            // Update on selected flow change
            model.on("change:selected_flow", () => {
                const newSelectedFlow = model.get("selected_flow");
                svg.selectAll("*").remove();
                const newG = svg.append("g").attr("transform", `translate(${margin.left}, ${margin.top})`);
                let newMetricScales = null;
                if (model.get("metric_mode")) {
                    newMetricScales = calculateMetricScales(processedData, data, model.get("metric_config"));
                }
                drawSankeyDiagram(newG, processedData, chartWidth, chartHeight, colorSchemes, newSelectedFlow, model, model.get("metric_mode"), newMetricScales, model.get("metric_config"));
                // No metric legend - removed
            });
        }

        function calculateMetricScales(processedData, rawData, metricConfig) {
            console.log("Calculating metric scales...");

            const perplexityValues = [];
            const coherenceValues = [];

            // Extract metric values from all nodes
            processedData.nodes.forEach(node => {
                const nodeData = rawData.nodes[node.id];
                if (nodeData) {
                    // Get perplexity from model_metrics
                    if (nodeData.model_metrics && nodeData.model_metrics.perplexity !== undefined) {
                        perplexityValues.push(nodeData.model_metrics.perplexity);
                    }

                    // Get coherence from mallet_diagnostics
                    if (nodeData.mallet_diagnostics && nodeData.mallet_diagnostics.coherence !== undefined) {
                        coherenceValues.push(nodeData.mallet_diagnostics.coherence);
                    }
                }
            });

            console.log(`Found ${perplexityValues.length} perplexity values, ${coherenceValues.length} coherence values`);

            if (perplexityValues.length === 0 || coherenceValues.length === 0) {
                console.warn("Insufficient metric data for metric mode");
                return null;
            }

            // Create scales
            const perplexityExtent = d3.extent(perplexityValues);
            const coherenceExtent = d3.extent(coherenceValues);

            console.log("Perplexity range:", perplexityExtent);
            console.log("Coherence range:", coherenceExtent);

            // Perplexity: lower is better, so we invert the scale (low perplexity = high red intensity)
            const perplexityScale = d3.scaleLinear()
                .domain(perplexityExtent)
                .range([1, 0]); // Inverted: low perplexity gets high value (more red)

            // Coherence: higher is better (less negative), but values are negative
            // More negative = worse, less negative = better
            const coherenceScale = d3.scaleLinear()
                .domain(coherenceExtent)
                .range([0, 1]); // Less negative coherence gets high value (more blue)

            return {
                perplexity: perplexityScale,
                coherence: coherenceScale,
                perplexityExtent,
                coherenceExtent
            };
        }

        function getMetricColor(nodeId, rawData, metricScales, metricConfig) {
            if (!metricScales) return "#666";

            const nodeData = rawData.nodes[nodeId];
            if (!nodeData) return "#666";

            let perplexityValue = null;
            let coherenceValue = null;

            // Get perplexity
            if (nodeData.model_metrics && nodeData.model_metrics.perplexity !== undefined) {
                perplexityValue = nodeData.model_metrics.perplexity;
            }

            // Get coherence
            if (nodeData.mallet_diagnostics && nodeData.mallet_diagnostics.coherence !== undefined) {
                coherenceValue = nodeData.mallet_diagnostics.coherence;
            }

            // If missing either metric, return gray
            if (perplexityValue === null || coherenceValue === null) {
                return "#999";
            }

            // Calculate normalized scores (0-1)
            const redIntensity = metricScales.perplexity(perplexityValue); // Low perplexity = high red
            const blueIntensity = metricScales.coherence(coherenceValue); // High coherence = high blue

            // Debug logging
            console.log(`${nodeId}: perp=${perplexityValue.toFixed(3)} (red=${redIntensity.toFixed(3)}), coh=${coherenceValue.toFixed(3)} (blue=${blueIntensity.toFixed(3)})`);

            // Ensure minimum brightness to avoid too dark colors
            const minBrightness = 0.2; // Minimum 20% brightness

            // Calculate color components with minimum brightness
            const red = Math.round(255 * Math.max(minBrightness, redIntensity * metricConfig.red_weight));
            const blue = Math.round(255 * Math.max(minBrightness, blueIntensity * metricConfig.blue_weight));
            const green = 0; // Pure red-blue spectrum

            // Ensure values are in valid range
            const clampedRed = Math.max(0, Math.min(255, red));
            const clampedBlue = Math.max(0, Math.min(255, blue));
            const clampedGreen = 0;

            const finalColor = `rgb(${clampedRed}, ${clampedGreen}, ${clampedBlue})`;
            console.log(`${nodeId}: Final color = ${finalColor}`);

            return finalColor;
        }

        function drawMetricLegend(svg, metricScales, metricConfig, width, height, margin) {
            const legend = svg.append("g")
                .attr("class", "metric-legend")
                .attr("transform", `translate(${margin.left}, ${height - margin.bottom + 10})`);

            // Title
            legend.append("text")
                .attr("x", 0)
                .attr("y", 0)
                .style("font-size", "12px")
                .style("font-weight", "bold")
                .style("fill", "#333")
                .text("Metric Mode: Perplexity (Red) × Coherence (Blue) = Quality (Purple)");

            // Color gradient demonstration
            const gradientWidth = 200;
            const gradientHeight = 15;

            // Create gradient definition
            const defs = svg.append("defs");

            const gradient = defs.append("linearGradient")
                .attr("id", "metric-gradient")
                .attr("x1", "0%")
                .attr("x2", "100%")
                .attr("y1", "0%")
                .attr("y2", "0%");

            // Add gradient stops to show the correct color mapping
            const stops = [
                { offset: "0%", color: "rgb(255, 0, 0)" },     // Pure red (high perplexity, low coherence)
                { offset: "25%", color: "rgb(200, 0, 55)" },   // Red-purple (high perplexity, medium coherence)  
                { offset: "50%", color: "rgb(128, 0, 128)" },  // Pure purple (medium perplexity, medium coherence)
                { offset: "75%", color: "rgb(55, 0, 200)" },   // Blue-purple (low perplexity, high coherence)
                { offset: "100%", color: "rgb(0, 0, 255)" }    // Pure blue (low perplexity, high coherence)
            ];

            stops.forEach(stop => {
                gradient.append("stop")
                    .attr("offset", stop.offset)
                    .attr("stop-color", stop.color);
            });

            // Draw gradient bar
            legend.append("rect")
                .attr("x", 0)
                .attr("y", 15)
                .attr("width", gradientWidth)
                .attr("height", gradientHeight)
                .attr("fill", "url(#metric-gradient)")
                .attr("stroke", "#333")
                .attr("stroke-width", 1);

            // Add labels with correct interpretation
            legend.append("text")
                .attr("x", 0)
                .attr("y", 45)
                .style("font-size", "10px")
                .style("fill", "#d62728")
                .text("Poor Quality");

            legend.append("text")
                .attr("x", gradientWidth/2)
                .attr("y", 45)
                .attr("text-anchor", "middle")
                .style("font-size", "10px")
                .style("fill", "#7f4f7f")
                .text("Good Quality");

            legend.append("text")
                .attr("x", gradientWidth)
                .attr("y", 45)
                .attr("text-anchor", "end")
                .style("font-size", "10px")
                .style("fill", "#2f2fdf")
                .text("Excellent Quality");

            // Show current ranges with better formatting
            legend.append("text")
                .attr("x", gradientWidth + 20)
                .attr("y", 20)
                .style("font-size", "9px")
                .style("fill", "#666")
                .text(`Perplexity: ${metricScales.perplexityExtent[1].toFixed(2)} (poor) - ${metricScales.perplexityExtent[0].toFixed(2)} (good)`);

            legend.append("text")
                .attr("x", gradientWidth + 20)
                .attr("y", 35)
                .style("font-size", "9px")
                .style("fill", "#666")
                .text(`Coherence: ${metricScales.coherenceExtent[0].toFixed(2)} (poor) - ${metricScales.coherenceExtent[1].toFixed(2)} (good)`);
        }

        function processDataForVisualization(data) {
            const nodes = [];
            const flows = [];
            const kValues = data.k_range || [];

            // Process nodes - convert from dictionary to array
            Object.entries(data.nodes || {}).forEach(([nodeName, nodeData]) => {
                const match = nodeName.match(/K(\\d+)_MC(\\d+)/);
                if (match) {
                    const k = parseInt(match[1]);
                    const mc = parseInt(match[2]);

                    nodes.push({
                        id: nodeName,
                        k: k,
                        mc: mc,
                        highCount: nodeData.high_count || 0,
                        mediumCount: nodeData.medium_count || 0,
                        totalProbability: nodeData.total_probability || 0,
                        highSamples: nodeData.high_samples || [],
                        mediumSamples: nodeData.medium_samples || []
                    });
                }
            });

            // Process flows
            (data.flows || []).forEach(flow => {
                flows.push({
                    source: flow.source_segment,
                    target: flow.target_segment,
                    sourceK: flow.source_k,
                    targetK: flow.target_k,
                    sampleCount: flow.sample_count || 0,
                    averageProbability: flow.average_probability || 0,
                    samples: flow.samples || []
                });
            });

            console.log(`Processed ${nodes.length} nodes and ${flows.length} flows`);
            return { nodes, flows, kValues };
        }

        function drawSankeyDiagram(g, data, width, height, colorSchemes, selectedFlow, model, metricMode, metricScales, metricConfig) {
            const { nodes, flows, kValues } = data;
            const rawData = model.get("sankey_data");

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

            // Filter flows - only show flows with 10+ samples
            const significantFlows = flows.filter(flow => flow.sampleCount >= 10);
            console.log(`Showing ${significantFlows.length} flows out of ${flows.length} (filtered flows < 10 samples)`);

            // Calculate positions with barycenter optimization
            const kSpacing = width / Math.max(1, kValues.length - 1);
            const nodesByK = d3.group(nodes, d => d.k);

            // Find max total count for scaling node heights
            const maxTotalCount = d3.max(nodes, d => d.highCount + d.mediumCount) || 1;
            const minNodeHeight = 20;
            const maxNodeHeight = 120;

            // Apply barycenter method for node ordering
            const optimizedNodePositions = optimizeNodeOrder(nodes, significantFlows, kValues, nodesByK, height);

            // Position nodes using optimized order
            nodes.forEach(node => {
                const kIndex = kValues.indexOf(node.k);
                node.x = kIndex * kSpacing;
                node.y = optimizedNodePositions[node.id];

                // Set node height based on total sample count (proportional scaling)
                const totalSamples = node.highCount + node.mediumCount;
                node.height = minNodeHeight + (totalSamples / maxTotalCount) * (maxNodeHeight - minNodeHeight);
            });

            // Calculate flow width scaling
            const maxFlowCount = d3.max(significantFlows, d => d.sampleCount) || 1;
            const minFlowWidth = 2;
            const maxFlowWidth = 25;

            // Draw flows first (behind nodes)
            const flowGroup = g.append("g").attr("class", "flows");

            significantFlows.forEach((flow, flowIndex) => {
                // Parse source and target segment names
                const sourceTopicId = flow.source.replace(/_high$|_medium$/, '');
                const targetTopicId = flow.target.replace(/_high$|_medium$/, '');
                const sourceLevel = flow.source.includes('_high') ? 'high' : 'medium';
                const targetLevel = flow.target.includes('_high') ? 'high' : 'medium';

                const sourceNode = nodes.find(n => n.id === sourceTopicId);
                const targetNode = nodes.find(n => n.id === targetTopicId);

                if (sourceNode && targetNode && flow.sampleCount > 0) {
                    // Proportional flow width scaling
                    const flowWidth = minFlowWidth + (flow.sampleCount / maxFlowCount) * (maxFlowWidth - minFlowWidth);

                    // Calculate connection points on the stacked bars
                    const sourceY = calculateSegmentY(sourceNode, sourceLevel);
                    const targetY = calculateSegmentY(targetNode, targetLevel);

                    // Create curved path
                    const curvePath = createCurvePath(
                        sourceNode.x + 15, sourceY,
                        targetNode.x - 15, targetY
                    );

                    // Check if this flow is selected
                    const isSelected = selectedFlow && 
                        selectedFlow.source === flow.source && 
                        selectedFlow.target === flow.target &&
                        selectedFlow.sourceK === flow.sourceK &&
                        selectedFlow.targetK === flow.targetK;

                    flowGroup.append("path")
                        .attr("d", curvePath)
                        .attr("stroke", isSelected ? "#ff6b35" : "#888")
                        .attr("stroke-width", isSelected ? flowWidth + 3 : flowWidth)
                        .attr("fill", "none")
                        .attr("opacity", isSelected ? 1.0 : 0.6)
                        .attr("class", `flow-${flowIndex}`)
                        .style("cursor", "pointer")
                        .on("mouseover", function(event) {
                            if (!isSelected) {
                                d3.select(this).attr("opacity", 0.8);
                            }
                            showTooltip(g, event, flow);
                        })
                        .on("mouseout", function() {
                            if (!isSelected) {
                                d3.select(this).attr("opacity", 0.6);
                            }
                            g.selectAll(".tooltip").remove();
                        })
                        .on("click", function(event) {
                            event.stopPropagation();
                            console.log("Flow clicked:", flow);

                            // Clear previous selection or select new flow
                            if (isSelected) {
                                model.set("selected_flow", {});
                            } else {
                                model.set("selected_flow", {
                                    source: flow.source,
                                    target: flow.target,
                                    sourceK: flow.sourceK,
                                    targetK: flow.targetK,
                                    samples: flow.samples,
                                    sampleCount: flow.sampleCount
                                });
                            }
                            model.save_changes();
                        });
                }
            });

            // Create sample tracing layer (initially empty)
            const tracingGroup = g.append("g").attr("class", "sample-tracing");

            // Draw nodes as stacked bars
            const nodeGroup = g.append("g").attr("class", "nodes");

            nodes.forEach(node => {
                const nodeG = nodeGroup.append("g")
                    .attr("class", "node")
                    .attr("transform", `translate(${node.x}, ${node.y - node.height/2})`);

                // Determine base color based on mode
                let baseColor;
                if (metricMode && metricScales) {
                    baseColor = getMetricColor(node.id, rawData, metricScales, metricConfig);
                } else {
                    baseColor = colorSchemes[node.k] || "#666";
                }

                // Calculate segment heights proportionally
                const totalCount = node.highCount + node.mediumCount;
                let highHeight = 0;
                let mediumHeight = 0;

                if (totalCount > 0) {
                    highHeight = (node.highCount / totalCount) * node.height;
                    mediumHeight = (node.mediumCount / totalCount) * node.height;
                }

                // In metric mode, use uniform colors; in default mode, use darker/lighter
                if (highHeight > 0) {
                    const highColor = metricMode ? baseColor : d3.color(baseColor).darker(0.8);

                    nodeG.append("rect")
                        .attr("x", -10)
                        .attr("y", 0)
                        .attr("width", 20)
                        .attr("height", highHeight)
                        .attr("fill", highColor)
                        .attr("stroke", "white")
                        .attr("stroke-width", 1)
                        .attr("class", `segment-${node.id}-high`)
                        .style("cursor", "pointer")
                        .on("mouseover", function(event) {
                            d3.select(this).attr("opacity", 0.8);
                            showSegmentTooltip(g, event, node, 'high', node.highCount, rawData, metricMode);
                        })
                        .on("mouseout", function() {
                            d3.select(this).attr("opacity", 1);
                            g.selectAll(".tooltip").remove();
                        });
                }

                // Draw medium representation segment with hover
                if (mediumHeight > 0) {
                    const mediumColor = metricMode ? baseColor : baseColor;

                    nodeG.append("rect")
                        .attr("x", -10)
                        .attr("y", highHeight)
                        .attr("width", 20)
                        .attr("height", mediumHeight)
                        .attr("fill", mediumColor)
                        .attr("stroke", "white")
                        .attr("stroke-width", 1)
                        .attr("class", `segment-${node.id}-medium`)
                        .style("cursor", "pointer")
                        .on("mouseover", function(event) {
                            d3.select(this).attr("opacity", 0.8);
                            showSegmentTooltip(g, event, node, 'medium', node.mediumCount, rawData, metricMode);
                        })
                        .on("mouseout", function() {
                            d3.select(this).attr("opacity", 1);
                            g.selectAll(".tooltip").remove();
                        });
                }

                // Add node label (only MC number, no sample count)
                nodeG.append("text")
                    .attr("x", 25)
                    .attr("y", node.height / 2)
                    .attr("dy", "0.35em")
                    .style("font-size", "11px")
                    .style("font-weight", "bold")
                    .style("fill", "#333")
                    .text(`MC${node.mc}`)
                    .style("cursor", "pointer")
                    .on("click", function() {
                        console.log("Node clicked:", node);
                    });
            });

            // Add click handler to clear selection when clicking on background
            g.on("click", function() {
                model.set("selected_flow", {});
                model.save_changes();
            });

            // Add K value labels at the top
            kValues.forEach((k, index) => {
                const labelColor = metricMode ? "#333" : (colorSchemes[k] || "#333");
                g.append("text")
                    .attr("x", index * kSpacing)
                    .attr("y", -30)
                    .attr("text-anchor", "middle")
                    .style("font-size", "16px")
                    .style("font-weight", "bold")
                    .style("fill", labelColor)
                    .text(`K=${k}`);
            });

            // Add legend in bottom-left corner to avoid overlap
            const legend = g.append("g")
                .attr("class", "legend")
                .attr("transform", `translate(20, ${height - 120})`); // Bottom-left positioning

            if (!metricMode) {
                // Default mode: show high/medium representation legend
                legend.append("rect")
                    .attr("width", 15)
                    .attr("height", 10)
                    .attr("fill", "#333");

                legend.append("text")
                    .attr("x", 20)
                    .attr("y", 8)
                    .style("font-size", "10px")
                    .text("High (≥0.67)");

                legend.append("rect")
                    .attr("y", 15)
                    .attr("width", 15)
                    .attr("height", 10)
                    .attr("fill", "#666");

                legend.append("text")
                    .attr("x", 20)
                    .attr("y", 23)
                    .style("font-size", "10px")
                    .text("Medium (0.33-0.66)");
            } else {
                // Metric mode: show metric interpretation legend
                legend.append("text")
                    .attr("x", 0)
                    .attr("y", 8)
                    .style("font-size", "10px")
                    .style("font-weight", "bold")
                    .style("fill", "#333")
                    .text("Metric Mode Active");

                legend.append("text")
                    .attr("x", 0)
                    .attr("y", 20)
                    .style("font-size", "9px")
                    .style("fill", "#d62728")
                    .text("Red: Low Perplexity");

                legend.append("text")
                    .attr("x", 0)
                    .attr("y", 32)
                    .style("font-size", "9px")
                    .style("fill", "#2ca02c")
                    .text("Blue: High Coherence");

                legend.append("text")
                    .attr("x", 0)
                    .attr("y", 44)
                    .style("font-size", "9px")
                    .style("fill", "#7f4f7f")
                    .text("Purple: Optimal Topics");

                // Add note about uniform colors in metric mode
                legend.append("text")
                    .attr("x", 0)
                    .attr("y", 56)
                    .style("font-size", "8px")
                    .style("fill", "#888")
                    .text("(Uniform colors - quality by hue)");
            }

            // Add flow info
            legend.append("text")
                .attr("x", 0)
                .attr("y", metricMode ? 72 : 40)
                .style("font-size", "9px")
                .style("fill", "#666")
                .text(`Flows: ${significantFlows.length} (≥10 samples)`);

            legend.append("text")
                .attr("x", 0)
                .attr("y", metricMode ? 84 : 52)
                .style("font-size", "9px")
                .style("fill", "#888")
                .text("Barycenter optimized");

            legend.append("text")
                .attr("x", 0)
                .attr("y", metricMode ? 96 : 64)
                .style("font-size", "9px")
                .style("fill", "#ff6b35")
                .text("Click flows to trace samples");

            // Initial sample tracing if there's already a selected flow
            if (selectedFlow && Object.keys(selectedFlow).length > 0) {
                updateSampleTracing(g, data, selectedFlow, nodes, significantFlows, kValues);
            }
        }

        function updateSampleTracing(g, data, selectedFlow, nodes, flows, kValues) {
            // Clear previous tracing
            g.selectAll(".sample-tracing").selectAll("*").remove();
            g.selectAll(".sample-count-badge").remove();
            g.selectAll(".sample-info-panel").remove();

            // Reset segment highlighting - set all segments back to white borders
            g.selectAll(".nodes rect").attr("stroke", "white").attr("stroke-width", 1);

            if (!selectedFlow || Object.keys(selectedFlow).length === 0) {
                return;
            }

            console.log("Tracing samples for selected flow:", selectedFlow);

            const tracingGroup = g.select(".sample-tracing");
            const samples = selectedFlow.samples || [];
            const sampleIds = samples.map(s => s.sample);

            console.log(`Tracing ${sampleIds.length} samples:`, sampleIds.slice(0, 3));

            if (sampleIds.length === 0) {
                showSampleInfo(g, selectedFlow, 0);
                return;
            }

            // Find where these samples are assigned across all K values
            const sampleAssignments = traceSampleAssignments(sampleIds, data, flows, kValues);

            // Draw sample trajectory paths with count-based line weights
            drawSampleTrajectories(tracingGroup, sampleAssignments, nodes, selectedFlow, data);

            // Highlight segments containing these samples
            highlightSampleSegments(g, sampleAssignments, nodes);

            // Show detailed sample info panel
            showSampleInfo(g, selectedFlow, sampleIds.length);
        }

        function traceSampleAssignments(sampleIds, data, flows, kValues) {
            console.log("Tracing sample assignments across K values...");
            const assignments = {};

            // Initialize assignment tracking for each sample
            sampleIds.forEach(sampleId => {
                assignments[sampleId] = {};
            });

            // Go through all flows to find where samples appear
            flows.forEach(flow => {
                if (flow.samples && flow.samples.length > 0) {
                    flow.samples.forEach(sampleData => {
                        const sampleId = sampleData.sample;

                        if (sampleIds.includes(sampleId)) {
                            // Extract topic and level from source segment
                            const sourceTopicId = flow.source.replace(/_high$|_medium$/, '');
                            const sourceLevel = flow.source.includes('_high') ? 'high' : 'medium';

                            // Extract topic and level from target segment  
                            const targetTopicId = flow.target.replace(/_high$|_medium$/, '');
                            const targetLevel = flow.target.includes('_high') ? 'high' : 'medium';

                            // Record source assignment
                            assignments[sampleId][flow.sourceK] = {
                                topicId: sourceTopicId,
                                level: sourceLevel,
                                probability: sampleData.source_prob || 0
                            };

                            // Record target assignment
                            assignments[sampleId][flow.targetK] = {
                                topicId: targetTopicId,
                                level: targetLevel,
                                probability: sampleData.target_prob || 0
                            };
                        }
                    });
                }
            });

            console.log("Sample assignments traced:", Object.keys(assignments).length, "samples");
            return assignments;
        }

        function drawSampleTrajectories(tracingGroup, sampleAssignments, nodes, selectedFlow, data) {
            const trajectoryColor = "#ff6b35";
            const sampleIds = Object.keys(sampleAssignments);

            console.log(`Drawing trajectories for ${sampleIds.length} samples`);

            // First, calculate sample counts for each segment to determine line weights
            const segmentCounts = {};
            Object.values(sampleAssignments).forEach(assignments => {
                Object.values(assignments).forEach(assignment => {
                    const segmentKey = `${assignment.topicId}-${assignment.level}`;
                    segmentCounts[segmentKey] = (segmentCounts[segmentKey] || 0) + 1;
                });
            });

            // Use the SAME scaling as the main sankey diagram flows
            const allFlows = data.flows.filter(flow => flow.sampleCount >= 10);
            const maxFlowCount = d3.max(allFlows, d => d.sampleCount) || 1;
            const minFlowWidth = 2;
            const maxFlowWidth = 25;

            // Function to get line weight using same formula as sankey flows
            const getSankeyLineWeight = (count) => {
                return minFlowWidth + (count / maxFlowCount) * (maxFlowWidth - minFlowWidth);
            };

            sampleIds.forEach((sampleId, sampleIndex) => {
                const assignments = sampleAssignments[sampleId];
                const pathPoints = [];

                // Convert assignments to path points with coordinates
                Object.entries(assignments).forEach(([k, assignment]) => {
                    const node = nodes.find(n => n.id === assignment.topicId);
                    if (node) {
                        const segmentY = calculateSegmentY(node, assignment.level);
                        pathPoints.push({
                            k: parseInt(k),
                            x: node.x,
                            y: segmentY,
                            topicId: assignment.topicId,
                            level: assignment.level,
                            probability: assignment.probability,
                            sampleCount: segmentCounts[`${assignment.topicId}-${assignment.level}`] || 0
                        });
                    }
                });

                // Sort path points by K value
                pathPoints.sort((a, b) => a.k - b.k);

                if (pathPoints.length >= 2) {
                    // Draw trajectory ONLY between adjacent K values
                    for (let i = 0; i < pathPoints.length - 1; i++) {
                        const start = pathPoints[i];
                        const end = pathPoints[i + 1];

                        // CRITICAL FIX: Only draw lines between adjacent K values
                        if (end.k - start.k === 1) {
                            // Check if this segment is the selected flow
                            const isSelectedSegment = 
                                start.k === selectedFlow.sourceK && 
                                end.k === selectedFlow.targetK;

                            // Calculate line weight using same scaling as sankey diagram
                            // Use the minimum sample count as the "flow capacity" between segments
                            const trajectoryFlowCount = Math.min(start.sampleCount, end.sampleCount);
                            const lineWeight = getSankeyLineWeight(trajectoryFlowCount);

                            const curvePath = createCurvePath(
                                start.x + 15, start.y,
                                end.x - 15, end.y
                            );

                            // ALL trajectory lines are now SOLID (no dashed lines)
                            tracingGroup.append("path")
                                .attr("d", curvePath)
                                .attr("stroke", trajectoryColor)
                                .attr("stroke-width", isSelectedSegment ? lineWeight + 2 : lineWeight)
                                .attr("stroke-dasharray", "none") // Always solid lines
                                .attr("fill", "none")
                                .attr("opacity", isSelectedSegment ? 0.9 : 0.7) // Slightly higher opacity for solid lines
                                .attr("class", `trajectory-${sampleIndex}-${i}`)
                                .style("pointer-events", "none");
                        }
                        // If end.k - start.k > 1, we skip drawing the line (gap in trajectory)
                    }

                    // Add dots at each assignment point (size proportional to sample count)
                    const maxSampleCount = Math.max(...Object.values(segmentCounts));
                    pathPoints.forEach((point, pointIndex) => {
                        // Scale dot size based on sample count using sankey proportions
                        const baseDotSize = 3;
                        const maxDotSize = 8; // Slightly larger to match sankey scale
                        const dotRadius = maxSampleCount > 0 ? 
                            baseDotSize + (point.sampleCount / maxSampleCount) * (maxDotSize - baseDotSize) : 
                            baseDotSize;

                        tracingGroup.append("circle")
                            .attr("cx", point.x)
                            .attr("cy", point.y)
                            .attr("r", dotRadius)
                            .attr("fill", trajectoryColor)
                            .attr("stroke", "white")
                            .attr("stroke-width", 1.5)
                            .attr("opacity", 0.8)
                            .attr("class", `trajectory-point-${sampleIndex}-${pointIndex}`)
                            .style("pointer-events", "none");
                    });
                }
            });

            console.log("Sample trajectories drawn with sankey-matching line weights (all solid)");
        }

        function highlightSampleSegments(g, sampleAssignments, nodes) {
            const highlightColor = "#ff6b35";

            // Count how many samples are in each segment
            const segmentCounts = {};

            Object.values(sampleAssignments).forEach(assignments => {
                Object.values(assignments).forEach(assignment => {
                    const segmentKey = `${assignment.topicId}-${assignment.level}`;
                    segmentCounts[segmentKey] = (segmentCounts[segmentKey] || 0) + 1;
                });
            });

            console.log("Segment counts:", segmentCounts);

            // Highlight segments and add count badges
            Object.entries(segmentCounts).forEach(([segmentKey, count]) => {
                const [topicId, level] = segmentKey.split('-');

                // Highlight the segment with orange border
                g.selectAll(`.segment-${topicId}-${level}`)
                    .attr("stroke", highlightColor)
                    .attr("stroke-width", 3);

                // Find the node to position the count badge
                const node = nodes.find(n => n.id === topicId);
                if (node) {
                    const badgeY = level === 'high' ? 
                        node.y - node.height/2 + 15 : 
                        node.y + node.height/2 - 15;

                    // Add count badge
                    g.append("circle")
                        .attr("cx", node.x + 35)
                        .attr("cy", badgeY)
                        .attr("r", 10)
                        .attr("fill", highlightColor)
                        .attr("stroke", "white")
                        .attr("stroke-width", 2)
                        .attr("class", "sample-count-badge");

                    g.append("text")
                        .attr("x", node.x + 35)
                        .attr("y", badgeY)
                        .attr("text-anchor", "middle")
                        .attr("dy", "0.35em")
                        .style("font-size", "9px")
                        .style("font-weight", "bold")
                        .style("fill", "white")
                        .text(count)
                        .attr("class", "sample-count-badge");
                }
            });
        }

        function optimizeNodeOrder(nodes, flows, kValues, nodesByK, height) {
            console.log("Applying barycenter method for node ordering...");

            const nodePositions = {};

            // Step 1: Initialize first K level with evenly spaced positions
            const firstK = kValues[0];
            const firstKNodes = nodesByK.get(firstK) || [];
            const spacing = height / Math.max(1, firstKNodes.length + 1);

            firstKNodes.forEach((node, index) => {
                nodePositions[node.id] = (index + 1) * spacing;
            });

            console.log(`Initialized K=${firstK} with ${firstKNodes.length} nodes`);

            // Step 2: For each subsequent K level, calculate barycenter positions
            for (let kIndex = 1; kIndex < kValues.length; kIndex++) {
                const currentK = kValues[kIndex];
                const prevK = kValues[kIndex - 1];
                const currentKNodes = nodesByK.get(currentK) || [];

                console.log(`Optimizing K=${currentK} (${currentKNodes.length} nodes)`);

                // Calculate barycenter for each node in current K level
                const barycenterData = currentKNodes.map(node => {
                    const nodeId = node.id;
                    let weightedSum = 0;
                    let totalWeight = 0;

                    // Find all flows coming TO this node from previous K level
                    flows.forEach(flow => {
                        const sourceTopicId = flow.source.replace(/_high$|_medium$/, '');
                        const targetTopicId = flow.target.replace(/_high$|_medium$/, '');

                        if (targetTopicId === nodeId && flow.sourceK === prevK) {
                            const sourcePosition = nodePositions[sourceTopicId];
                            if (sourcePosition !== undefined) {
                                const weight = flow.sampleCount;
                                weightedSum += sourcePosition * weight;
                                totalWeight += weight;
                            }
                        }
                    });

                    // Calculate barycenter (weighted average position)
                    const barycenter = totalWeight > 0 ? weightedSum / totalWeight : height / 2;

                    return {
                        node: node,
                        barycenter: barycenter,
                        totalWeight: totalWeight
                    };
                });

                // Sort nodes by barycenter value
                barycenterData.sort((a, b) => a.barycenter - b.barycenter);

                // Assign new positions based on sorted order
                const newSpacing = height / Math.max(1, barycenterData.length + 1);
                barycenterData.forEach((data, index) => {
                    nodePositions[data.node.id] = (index + 1) * newSpacing;
                });
            }

            console.log("Barycenter optimization complete!");
            return nodePositions;
        }

        function calculateSegmentY(node, level) {
            const totalCount = node.highCount + node.mediumCount;
            if (totalCount === 0) return node.y;

            const highHeight = (node.highCount / totalCount) * node.height;

            if (level === 'high') {
                return node.y - node.height/2 + highHeight/2;
            } else {
                return node.y - node.height/2 + highHeight + (node.height - highHeight)/2;
            }
        }

        function createCurvePath(x1, y1, x2, y2) {
            const midX = (x1 + x2) / 2;
            return `M ${x1} ${y1} C ${midX} ${y1} ${midX} ${y2} ${x2} ${y2}`;
        }

        function showTooltip(g, event, flow) {
            const tooltip = g.append("g").attr("class", "tooltip");

            const tooltipText = `${flow.sampleCount} samples\\n${flow.source} → ${flow.target}`;
            const lines = tooltipText.split('\\n');

            const tooltipWidth = 160;
            const tooltipHeight = 35;

            // Get the chart dimensions to ensure tooltip stays within bounds
            const chartWidth = g.node().getBBox().width || 1000;

            // Calculate tooltip position with bounds checking
            let tooltipX = event.layerX || 0;
            let tooltipY = (event.layerY || 0) - 40;

            // Adjust X position if tooltip would go off the right edge
            if (tooltipX + tooltipWidth > chartWidth) {
                tooltipX = chartWidth - tooltipWidth - 10;
            }

            // Adjust Y position if tooltip would go off the top edge
            if (tooltipY < 0) {
                tooltipY = (event.layerY || 0) + 20; // Show below cursor instead
            }

            const rect = tooltip.append("rect")
                .attr("x", tooltipX)
                .attr("y", tooltipY)
                .attr("width", tooltipWidth)
                .attr("height", tooltipHeight)
                .attr("fill", "white")
                .attr("stroke", "black")
                .attr("rx", 3)
                .attr("opacity", 0.9);

            lines.forEach((line, i) => {
                tooltip.append("text")
                    .attr("x", tooltipX + 5)
                    .attr("y", tooltipY + 15 + i * 12)
                    .style("font-size", "10px")
                    .style("fill", "black")
                    .text(line);
            });
        }

        function showSampleInfo(g, selectedFlow, sampleCount) {
            const infoPanel = g.append("g").attr("class", "sample-info-panel");

            // Background panel
            infoPanel.append("rect")
                .attr("x", 10)
                .attr("y", 10)
                .attr("width", 200)
                .attr("height", 60)
                .attr("fill", "white")
                .attr("stroke", "#ff6b35")
                .attr("stroke-width", 2)
                .attr("rx", 5)
                .attr("opacity", 0.95);

            // Title
            infoPanel.append("text")
                .attr("x", 20)
                .attr("y", 30)
                .style("font-size", "12px")
                .style("font-weight", "bold")
                .style("fill", "#ff6b35")
                .text(`Selected: ${sampleCount} Samples`);

            // Flow info
            infoPanel.append("text")
                .attr("x", 20)
                .attr("y", 45)
                .style("font-size", "10px")
                .style("fill", "#333")
                .text(`${selectedFlow.source} → ${selectedFlow.target}`);

            // Instructions
            infoPanel.append("text")
                .attr("x", 20)
                .attr("y", 58)
                .style("font-size", "9px")
                .style("fill", "#666")
                .text("Click flow again or background to clear");
        }

        function showSegmentTooltip(g, event, node, level, count, rawData, metricMode) {
            const tooltip = g.append("g").attr("class", "tooltip");

            const levelText = level === 'high' ? 'High (≥0.67)' : 'Medium (0.33-0.66)';
            let tooltipLines = [`${node.id}`, levelText, `${count} samples`];

            // Add metric information if in metric mode
            if (metricMode && rawData && rawData.nodes[node.id]) {
                const nodeData = rawData.nodes[node.id];

                if (nodeData.model_metrics && nodeData.model_metrics.perplexity !== undefined) {
                    tooltipLines.push(`Perplexity: ${nodeData.model_metrics.perplexity.toFixed(3)}`);
                }

                if (nodeData.mallet_diagnostics && nodeData.mallet_diagnostics.coherence !== undefined) {
                    tooltipLines.push(`Coherence: ${nodeData.mallet_diagnostics.coherence.toFixed(3)}`);
                }
            }

            const tooltipHeight = tooltipLines.length * 12 + 10;
            const tooltipWidth = Math.max(140, Math.max(...tooltipLines.map(line => line.length * 6 + 10)));

            // Get the chart dimensions to ensure tooltip stays within bounds
            const chartWidth = g.node().getBBox().width || 1000;

            // Calculate tooltip position with bounds checking
            let tooltipX = event.layerX || 0;
            let tooltipY = (event.layerY || 0) - tooltipHeight - 10;

            // Adjust X position if tooltip would go off the right edge
            if (tooltipX + tooltipWidth > chartWidth) {
                tooltipX = chartWidth - tooltipWidth - 10;
            }

            // Adjust Y position if tooltip would go off the top edge
            if (tooltipY < 0) {
                tooltipY = (event.layerY || 0) + 20; // Show below cursor instead
            }

            const rect = tooltip.append("rect")
                .attr("x", tooltipX)
                .attr("y", tooltipY)
                .attr("width", tooltipWidth)
                .attr("height", tooltipHeight)
                .attr("fill", "white")
                .attr("stroke", "black")
                .attr("rx", 3)
                .attr("opacity", 0.9);

            tooltipLines.forEach((line, i) => {
                tooltip.append("text")
                    .attr("x", tooltipX + 5)
                    .attr("y", tooltipY + 15 + i * 12)
                    .style("font-size", "10px")
                    .style("fill", "black")
                    .text(line);
            });
        }

        export default { render };
        """

        _css = """
        .widget-container {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
        }

        .sample-tracing {
            pointer-events: none;
        }

        .sample-info-panel {
            pointer-events: none;
        }

        .metric-legend {
            pointer-events: none;
        }
        """

        # Widget traits
        sankey_data = traitlets.Dict(default_value={}).tag(sync=True)
        width = traitlets.Int(default_value=1200).tag(sync=True)
        height = traitlets.Int(default_value=800).tag(sync=True)

        # Add trait for tracking selected flow
        selected_flow = traitlets.Dict(default_value={}).tag(sync=True)

        # Add traits for metric mode
        metric_mode = traitlets.Bool(default_value=False).tag(sync=True)
        metric_config = traitlets.Dict(default_value={
            'red_weight': 0.8,    # Weight for perplexity (red component)
            'blue_weight': 0.8,   # Weight for coherence (blue component)
            'min_saturation': 0.3  # Minimum color saturation to keep colors visible
        }).tag(sync=True)

        color_schemes = traitlets.Dict(default_value={
            2: "#1f77b4", 3: "#ff7f0e", 4: "#2ca02c", 5: "#d62728", 6: "#9467bd",
            7: "#8c564b", 8: "#e377c2", 9: "#7f7f7f", 10: "#bcbd22"
        }).tag(sync=True)

        def __init__(self, sankey_data=None, mode="default", **kwargs):
            super().__init__(**kwargs)
            if sankey_data:
                self.sankey_data = sankey_data
            # Set metric_mode based on the mode parameter
            self.metric_mode = (mode == "metric")

        def set_mode(self, mode):
            """Set visualization mode: 'default' or 'metric'"""
            self.metric_mode = (mode == "metric")
            return self  # Return self for chaining

        def update_metric_config(self, red_weight=None, blue_weight=None, min_saturation=None):
            """Update metric mode configuration"""
            config = self.metric_config.copy()
            if red_weight is not None:
                config['red_weight'] = red_weight
            if blue_weight is not None:
                config['blue_weight'] = blue_weight
            if min_saturation is not None:
                config['min_saturation'] = min_saturation
            self.metric_config = config
            return self  # Return self for chaining
    return (StripeSankeyInline,)


@app.cell
def _(mo):
    mo.md(r"""## Plot""")
    return


@app.cell
def _(mo):
    mode_dropdown = mo.ui.dropdown(
        options=["default", "metric"],
        value="default",
        label="Visualization Mode"
    )
    return (mode_dropdown,)


@app.cell
def _(StripeSankeyInline, fully_integrated_data, mode_dropdown):
    real_sankey_widget = StripeSankeyInline(
        sankey_data=fully_integrated_data,
        mode=mode_dropdown.value  # This will reactively update
    )
    return (real_sankey_widget,)


@app.cell
def _(mode_dropdown):
    mode_dropdown
    return


@app.cell
def _(real_sankey_widget):
    real_sankey_widget
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
