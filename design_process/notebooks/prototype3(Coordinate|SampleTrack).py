import marimo

__generated_with = "0.14.10"
app = marimo.App(width="medium")


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
    return ET, anywidget, defaultdict, glob, json, np, os, pd, re, traitlets


@app.cell
def _(pd):
    metadata_df= pd.read_csv('/Users/huopeiyang/Library/CloudStorage/OneDrive-KULeuven/py_working/Luke_data/Luke_WP1/data/metadata_new_updated.csv', index_col=0)
    selected_metadata=["Country", 'Breed_type', 'Outdoor_access', 'Bedding_present', 'Slatted floor', "Age_category"]
    MC_feature_folder_path = "/Users/huopeiyang/Library/CloudStorage/OneDrive-KULeuven/py_working/LDA_workflow/VIZ_design/9Models_Luke/ASVProbabilities"  # Folder with ASVProbabilities files
    Sample_MC_folder_path = "/Users/huopeiyang/Library/CloudStorage/OneDrive-KULeuven/py_working/LDA_workflow/VIZ_design/9Models_Luke/SampleProbabilities_wide"
    return MC_feature_folder_path, Sample_MC_folder_path


@app.cell
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
    return (sankey_data,)


@app.cell
def _(anywidget, traitlets):
    class CoordinateAxesLayout(anywidget.AnyWidget):
        _esm = """
        import * as d3 from "https://cdn.skypack.dev/d3@7";

        function render({ model, el }) {
            el.innerHTML = '';

            const width = model.get("width");
            const height = model.get("height");
            const nodeHeight = model.get("node_height");
            const nodeWidth = model.get("node_width");
            const colorSchemes = model.get("color_schemes");
            const nodesData = model.get("nodes_data");
            const enableCrossingReduction = model.get("enable_crossing_reduction");

            // Create SVG
            const svg = d3.select(el)
                .append("svg")
                .attr("width", width)
                .attr("height", height)
                .style("background", "#fafafa")
                .style("border", "1px solid #ddd");

            const margin = { top: 60, right: 150, bottom: 40, left: 100 };
            const chartWidth = width - margin.left - margin.right;
            const chartHeight = height - margin.top - margin.bottom;

            const g = svg.append("g")
                .attr("transform", `translate(${margin.left}, ${margin.top})`);

            // Draw the visualization
            drawVisualization(g, nodesData, chartWidth, chartHeight, nodeHeight, nodeWidth, colorSchemes, enableCrossingReduction, model);
        }

        function drawVisualization(g, nodesData, width, height, nodeHeight, nodeWidth, colorSchemes, enableCrossingReduction, model) {
            // Extract K values and create x scale
            const kValues = [...new Set(nodesData.map(n => n.k))].sort((a, b) => a - b);
            const xScale = d3.scalePoint()
                .domain(kValues)
                .range([0, width])
                .padding(0.1);

            // Find min and max sample counts for scaling
            const sampleCounts = nodesData.map(n => n.samples ? n.samples.length : 0);
            const minSampleCount = Math.min(...sampleCounts);
            const maxSampleCount = Math.max(...sampleCounts);

            // Create width scale
            const minNodeWidth = nodeWidth * 0.5;
            const maxNodeWidth = nodeWidth * 1.5;
            const widthScale = d3.scaleLinear()
                .domain([minSampleCount, maxSampleCount])
                .range([minNodeWidth, maxNodeWidth]);

            // Position nodes with optional crossing reduction
            let nodePositions;
            if (enableCrossingReduction) {
                nodePositions = calculateOptimizedNodePositions(nodesData, kValues, height, nodeHeight);
            } else {
                nodePositions = calculateNodePositions(nodesData, kValues, height, nodeHeight);
            }

            // Apply positions and widths
            nodesData.forEach(node => {
                node.x = xScale(node.k);
                node.y = nodePositions[`${node.k}_${node.mc}`];
                node.scaledWidth = widthScale(node.samples ? node.samples.length : 0);
            });

            // Extract all unique sample IDs
            const allSampleIds = new Set();
            nodesData.forEach(node => {
                if (node.samples) {
                    node.samples.forEach(s => allSampleIds.add(s.id));
                }
            });

            // Create layers
            const sampleLineGroup = g.append("g").attr("class", "sample-lines");
            const axisGroup = g.append("g").attr("class", "axes");
            const brushGroup = g.append("g").attr("class", "brushes");

            // Store active brushes
            const activeBrushes = {};

            // Draw sample lines
            drawSampleLines(sampleLineGroup, nodesData, Array.from(allSampleIds), nodeHeight, activeBrushes);

            // Draw axes with brushes
            drawAxesWithBrushes(axisGroup, brushGroup, nodesData, nodeHeight, colorSchemes, activeBrushes, sampleLineGroup);

            // Add K labels
            kValues.forEach(k => {
                g.append("text")
                    .attr("x", xScale(k))
                    .attr("y", -30)
                    .attr("text-anchor", "middle")
                    .style("font-size", "16px")
                    .style("font-weight", "bold")
                    .style("fill", colorSchemes[k] || "#333")
                    .text(`K=${k}`);
            });

            // Add legend
            addLegend(g, width, allSampleIds.size, minSampleCount, maxSampleCount, enableCrossingReduction);
        }

        function calculateNodePositions(nodes, kValues, height, nodeHeight) {
            const positions = {};
            const nodesByK = d3.group(nodes, d => d.k);

            kValues.forEach(k => {
                const kNodes = nodesByK.get(k) || [];
                const numNodes = kNodes.length;

                if (numNodes === 0) return;

                // Sort by MC number
                kNodes.sort((a, b) => a.mc - b.mc);

                // Calculate spacing
                const totalNodeHeight = numNodes * nodeHeight;
                const totalSpacing = height - totalNodeHeight;
                const spaceBetween = totalSpacing / (numNodes + 1);

                kNodes.forEach((node, index) => {
                    const yPos = spaceBetween + index * (nodeHeight + spaceBetween) + nodeHeight / 2;
                    positions[`${node.k}_${node.mc}`] = yPos;
                });
            });

            return positions;
        }

        function calculateOptimizedNodePositions(nodes, kValues, height, nodeHeight) {
            const positions = {};
            const nodesByK = d3.group(nodes, d => d.k);

            // First, get initial positions with proper spacing
            const initialPositions = calculateNodePositions(nodes, kValues, height, nodeHeight);
            Object.assign(positions, initialPositions);

            // Build adjacency information
            const adjacency = buildAdjacency(nodes);

            // Apply barycenter method iteratively
            const maxIterations = 5;

            for (let iter = 0; iter < maxIterations; iter++) {
                let totalMovement = 0;

                // Process each K level independently
                for (let kIdx = 1; kIdx < kValues.length; kIdx++) {
                    const k = kValues[kIdx];
                    const prevK = kValues[kIdx - 1];

                    // Calculate optimal order based on previous K
                    const movement = optimizeKLevel(k, prevK, nodesByK, positions, adjacency, height, nodeHeight);
                    totalMovement += movement;
                }

                // Backward pass
                for (let kIdx = kValues.length - 2; kIdx >= 0; kIdx--) {
                    const k = kValues[kIdx];
                    const nextK = kValues[kIdx + 1];

                    const movement = optimizeKLevel(k, nextK, nodesByK, positions, adjacency, height, nodeHeight);
                    totalMovement += movement;
                }

                // Stop if converged
                if (totalMovement < 10) break;
            }

            return positions;
        }

        function optimizeKLevel(currentK, referenceK, nodesByK, positions, adjacency, height, nodeHeight) {
            const currentNodes = nodesByK.get(currentK) || [];
            if (currentNodes.length <= 1) return 0;

            // Calculate barycenter for each node
            const nodeScores = currentNodes.map(node => {
                const nodeKey = `${node.k}_${node.mc}`;
                const connections = adjacency[nodeKey] || {};

                let weightedSum = 0;
                let totalWeight = 0;

                Object.entries(connections).forEach(([connectedKey, weight]) => {
                    const [connK] = connectedKey.split('_').map(Number);
                    if (connK === referenceK && positions[connectedKey] !== undefined) {
                        weightedSum += positions[connectedKey] * weight;
                        totalWeight += weight;
                    }
                });

                // If no connections, use current position as score
                const score = totalWeight > 0 ? weightedSum / totalWeight : positions[nodeKey];

                return {
                    node: node,
                    nodeKey: nodeKey,
                    score: score,
                    hasConnections: totalWeight > 0
                };
            });

            // Sort by score (nodes with connections first, then by barycenter score)
            nodeScores.sort((a, b) => {
                if (a.hasConnections && !b.hasConnections) return -1;
                if (!a.hasConnections && b.hasConnections) return 1;
                return a.score - b.score;
            });

            // Calculate new positions with proper spacing
            const numNodes = currentNodes.length;
            const totalSpacing = height - (numNodes * nodeHeight);
            const spaceBetween = Math.max(20, totalSpacing / (numNodes + 1));

            let totalMovement = 0;

            nodeScores.forEach((item, index) => {
                const oldPos = positions[item.nodeKey];
                const newPos = spaceBetween + index * (nodeHeight + spaceBetween) + nodeHeight / 2;

                totalMovement += Math.abs(newPos - oldPos);
                positions[item.nodeKey] = newPos;
            });

            return totalMovement;
        }

        function buildAdjacency(nodes) {
            const adjacency = {};

            // Build sample to nodes mapping
            const sampleToNodes = {};
            nodes.forEach(node => {
                if (node.samples) {
                    node.samples.forEach(sample => {
                        if (!sampleToNodes[sample.id]) {
                            sampleToNodes[sample.id] = [];
                        }
                        sampleToNodes[sample.id].push({
                            k: node.k,
                            mc: node.mc,
                            prob: sample.probability
                        });
                    });
                }
            });

            // Build adjacency based on shared samples
            Object.values(sampleToNodes).forEach(sampleNodes => {
                sampleNodes.forEach((node1, i) => {
                    sampleNodes.forEach((node2, j) => {
                        if (i !== j && Math.abs(node1.k - node2.k) === 1) {
                            const key1 = `${node1.k}_${node1.mc}`;
                            const key2 = `${node2.k}_${node2.mc}`;

                            if (!adjacency[key1]) adjacency[key1] = {};
                            if (!adjacency[key2]) adjacency[key2] = {};

                            adjacency[key1][key2] = (adjacency[key1][key2] || 0) + 1;
                            adjacency[key2][key1] = (adjacency[key2][key1] || 0) + 1;
                        }
                    });
                });
            });

            return adjacency;
        }

        function applyBarycenter(currentK, referenceK, nodesByK, positions, adjacency, height, nodeHeight) {
            // This function is no longer needed - removed
            return 0;
        }

        function drawAxesWithBrushes(axisGroup, brushGroup, nodes, nodeHeight, colorSchemes, activeBrushes, sampleLineGroup) {
            nodes.forEach(node => {
                const nodeKey = `${node.k}_${node.mc}`;

                // Draw axis
                const axisG = axisGroup.append("g")
                    .attr("class", `axis-node-${node.k}-${node.mc}`)
                    .attr("transform", `translate(${node.x}, ${node.y})`);

                // Background
                axisG.append("rect")
                    .attr("x", -node.scaledWidth/2)
                    .attr("y", -nodeHeight/2)
                    .attr("width", node.scaledWidth)
                    .attr("height", nodeHeight)
                    .attr("fill", "white")
                    .attr("stroke", colorSchemes[node.k] || "#666")
                    .attr("stroke-width", 1)
                    .attr("opacity", 0.9);

                // Main axis line
                axisG.append("line")
                    .attr("x1", 0)
                    .attr("x2", 0)
                    .attr("y1", -nodeHeight/2 + 5)
                    .attr("y2", nodeHeight/2 - 5)
                    .attr("stroke", colorSchemes[node.k] || "#666")
                    .attr("stroke-width", 2);

                // Probability scale
                const yScale = d3.scaleLinear()
                    .domain([0, 1])
                    .range([nodeHeight/2 - 5, -nodeHeight/2 + 5]);

                // Draw scale
                drawProbabilityScale(axisG, yScale, node, colorSchemes);

                // Labels
                axisG.append("text")
                    .attr("x", 0)
                    .attr("y", -nodeHeight/2 - 8)
                    .attr("text-anchor", "middle")
                    .style("font-size", "11px")
                    .style("font-weight", "bold")
                    .style("fill", colorSchemes[node.k] || "#333")
                    .text(`MC${node.mc}`);

                axisG.append("text")
                    .attr("x", 0)
                    .attr("y", nodeHeight/2 + 15)
                    .attr("text-anchor", "middle")
                    .style("font-size", "9px")
                    .style("fill", "#666")
                    .text(`${node.samples ? node.samples.length : 0} samples`);

                // Add brush
                const brushG = brushGroup.append("g")
                    .attr("class", `brush-${nodeKey}`)
                    .attr("transform", `translate(${node.x}, ${node.y})`);

                const brush = d3.brushY()
                    .extent([[-node.scaledWidth/2 - 5, -nodeHeight/2 + 5], [node.scaledWidth/2 + 5, nodeHeight/2 - 5]])
                    .on("start brush end", function(event) {
                        handleBrush(event, nodeKey, yScale, activeBrushes, nodes, sampleLineGroup);
                    });

                brushG.call(brush);

                // Style brush handles
                brushG.selectAll(".handle")
                    .style("fill", colorSchemes[node.k] || "#666")
                    .style("opacity", 0.8);
            });
        }

        function drawProbabilityScale(axisG, yScale, node, colorSchemes) {
            const tickValues = [0, 0.25, 0.5, 0.75, 1];

            tickValues.forEach(tick => {
                const y = yScale(tick);

                // Ticks
                axisG.append("line")
                    .attr("x1", -Math.min(5, node.scaledWidth/4))
                    .attr("x2", Math.min(5, node.scaledWidth/4))
                    .attr("y1", y)
                    .attr("y2", y)
                    .attr("stroke", colorSchemes[node.k] || "#666")
                    .attr("stroke-width", 1);

                // Labels
                axisG.append("text")
                    .attr("x", -node.scaledWidth/2 - 5)
                    .attr("y", y)
                    .attr("text-anchor", "end")
                    .attr("dy", "0.35em")
                    .style("font-size", "8px")
                    .style("fill", "#666")
                    .text(tick.toFixed(1));
            });

            // Threshold lines
            [0.33, 0.67].forEach(threshold => {
                const y = yScale(threshold);
                axisG.append("line")
                    .attr("x1", -node.scaledWidth/2 + 5)
                    .attr("x2", node.scaledWidth/2 - 5)
                    .attr("y1", y)
                    .attr("y2", y)
                    .attr("stroke", "#999")
                    .attr("stroke-width", 0.5)
                    .attr("stroke-dasharray", "2,2");
            });
        }

        function handleBrush(event, nodeKey, yScale, activeBrushes, nodes, sampleLineGroup) {
            if (event.selection) {
                // Convert brush selection to probability range
                const [y1, y2] = event.selection;
                const probRange = [yScale.invert(y2), yScale.invert(y1)].sort((a, b) => a - b);
                activeBrushes[nodeKey] = probRange;
            } else {
                // Brush cleared
                delete activeBrushes[nodeKey];
            }

            // Update sample lines based on active brushes
            updateSampleLineHighlights(sampleLineGroup, nodes, activeBrushes);
        }

        function updateSampleLineHighlights(sampleLineGroup, nodes, activeBrushes) {
            const brushedNodes = Object.keys(activeBrushes);

            sampleLineGroup.selectAll(".sample-line").each(function(d) {
                const line = d3.select(this);
                const sampleId = line.attr("class").split(" ")[1].replace("sample-", "");

                let shouldHighlight = brushedNodes.length === 0; // Highlight all if no brushes

                if (brushedNodes.length > 0) {
                    // Check if sample passes all brush filters
                    shouldHighlight = brushedNodes.every(nodeKey => {
                        const [k, mc] = nodeKey.split("_").map(Number);
                        const node = nodes.find(n => n.k === k && n.mc === mc);

                        if (node && node.samples) {
                            const sample = node.samples.find(s => s.id === sampleId);
                            if (sample) {
                                const [minProb, maxProb] = activeBrushes[nodeKey];
                                return sample.probability >= minProb && sample.probability <= maxProb;
                            }
                        }
                        return false;
                    });
                }

                // Update line styling
                line.attr("stroke", shouldHighlight ? "#ff6b35" : "#888")
                    .attr("stroke-width", shouldHighlight ? 2 : 1)
                    .attr("opacity", shouldHighlight ? 0.8 : 0.2);

                // Update dots
                sampleLineGroup.selectAll(`.sample-${sampleId}-dot`)
                    .attr("fill", shouldHighlight ? "#ff6b35" : "#888")
                    .attr("r", shouldHighlight ? 3 : 2)
                    .attr("opacity", shouldHighlight ? 0.8 : 0.2);
            });
        }

        function drawSampleLines(lineGroup, nodes, sampleIds, nodeHeight, activeBrushes) {
            // Create probability scales for each node
            const nodeScales = {};
            nodes.forEach(node => {
                nodeScales[`${node.k}_${node.mc}`] = d3.scaleLinear()
                    .domain([0, 1])
                    .range([node.y + nodeHeight/2 - 5, node.y - nodeHeight/2 + 5]);
            });

            // Draw lines for each sample
            sampleIds.forEach((sampleId, idx) => {
                const lineData = [];

                // Find this sample across all nodes
                nodes.forEach(node => {
                    if (node.samples) {
                        const sampleData = node.samples.find(s => s.id === sampleId);
                        if (sampleData) {
                            lineData.push({
                                x: node.x,
                                y: nodeScales[`${node.k}_${node.mc}`](sampleData.probability),
                                k: node.k,
                                mc: node.mc,
                                prob: sampleData.probability
                            });
                        }
                    }
                });

                // Sort by K value
                lineData.sort((a, b) => a.k - b.k);

                if (lineData.length >= 2) {
                    // Create line generator
                    const line = d3.line()
                        .x(d => d.x)
                        .y(d => d.y)
                        .curve(d3.curveMonotoneX);

                    // Draw the line
                    lineGroup.append("path")
                        .datum(lineData)
                        .attr("d", line)
                        .attr("fill", "none")
                        .attr("stroke", "#888")
                        .attr("stroke-width", 1)
                        .attr("opacity", 0.4)
                        .attr("class", `sample-line sample-${sampleId}`)
                        // .on("mouseover", function(event) {
                        //    if (Object.keys(activeBrushes).length === 0) {
                        //        d3.select(this)
                        //            .attr("stroke-width", 2.5)
                        //            .attr("opacity", 1)
                        //            .attr("stroke", "#ff6b35");
                        //    }
                        //
                        //    // Show tooltip
                        //    showSampleTooltip(lineGroup, event, sampleId, lineData);
                        //})
                        //.on("mouseout", function() {
                        //    if (Object.keys(activeBrushes).length === 0) {
                        //       d3.select(this)
                        //            .attr("stroke-width", 1)
                        //            .attr("opacity", 0.4)
                        //            .attr("stroke", "#888");
                        //    }
                        //
                        //    lineGroup.selectAll(".tooltip").remove();
                        //});

                    // Add dots at each point
                    lineData.forEach(d => {
                        lineGroup.append("circle")
                            .attr("cx", d.x)
                            .attr("cy", d.y)
                            .attr("r", 2)
                            .attr("fill", "#888")
                            .attr("stroke", "white")
                            .attr("stroke-width", 0.5)
                            .attr("opacity", 0.6)
                            .attr("class", `sample-dot sample-${sampleId}-dot`);
                    });
                }
            });
        }

        function showSampleTooltip(g, event, sampleId, lineData) {
            const tooltip = g.append("g").attr("class", "tooltip");

            const avgProb = lineData.reduce((sum, d) => sum + d.prob, 0) / lineData.length;
            const path = lineData.map(d => `MC${d.mc}`).join(" → ");
            const text = `Sample: ${sampleId}\\nPath: ${path}\\nAvg prob: ${avgProb.toFixed(3)}`;

            const rect = tooltip.append("rect")
                .attr("x", event.layerX || 0)
                .attr("y", (event.layerY || 0) - 50)
                .attr("width", 200)
                .attr("height", 50)
                .attr("fill", "white")
                .attr("stroke", "black")
                .attr("rx", 3)
                .attr("opacity", 0.95);

            const lines = text.split("\\n");
            lines.forEach((line, i) => {
                tooltip.append("text")
                    .attr("x", (event.layerX || 0) + 5)
                    .attr("y", (event.layerY || 0) - 35 + i * 15)
                    .style("font-size", "10px")
                    .style("fill", "black")
                    .text(line);
            });
        }

        function addLegend(g, width, totalSamples, minSampleCount, maxSampleCount, crossingReduction) {
            const legend = g.append("g")
                .attr("class", "legend")
                .attr("transform", `translate(${width + 20}, 20)`);

            legend.append("text")
                .attr("x", 0)
                .attr("y", 0)
                .style("font-size", "12px")
                .style("font-weight", "bold")
                .text("Controls");

            // Brushing info
            legend.append("text")
                .attr("x", 0)
                .attr("y", 20)
                .style("font-size", "10px")
                .style("font-weight", "bold")
                .text("Brushing:");

            legend.append("text")
                .attr("x", 0)
                .attr("y", 35)
                .style("font-size", "9px")
                .style("fill", "#666")
                .text("Drag on axis to filter");

            legend.append("text")
                .attr("x", 0)
                .attr("y", 48)
                .style("font-size", "9px")
                .style("fill", "#666")
                .text("Clear: click outside");

            // Crossing reduction status
            legend.append("text")
                .attr("x", 0)
                .attr("y", 70)
                .style("font-size", "10px")
                .style("font-weight", "bold")
                .text("Layout:");

            legend.append("text")
                .attr("x", 0)
                .attr("y", 85)
                .style("font-size", "9px")
                .style("fill", crossingReduction ? "#2ecc71" : "#666")
                .text(crossingReduction ? "✓ Optimized" : "Default order");

            // Sample lines
            legend.append("line")
                .attr("x1", 0)
                .attr("x2", 20)
                .attr("y1", 105)
                .attr("y2", 105)
                .attr("stroke", "#888")
                .attr("stroke-width", 1)
                .attr("opacity", 0.4);

            legend.append("text")
                .attr("x", 25)
                .attr("y", 105)
                .attr("dy", "0.35em")
                .style("font-size", "10px")
                .text("Unselected");

            legend.append("line")
                .attr("x1", 0)
                .attr("x2", 20)
                .attr("y1", 120)
                .attr("y2", 120)
                .attr("stroke", "#ff6b35")
                .attr("stroke-width", 2);

            legend.append("text")
                .attr("x", 25)
                .attr("y", 120)
                .attr("dy", "0.35em")
                .style("font-size", "10px")
                .text("Brushed/Hovered");

            // Stats
            legend.append("text")
                .attr("x", 0)
                .attr("y", 145)
                .style("font-size", "10px")
                .style("fill", "#666")
                .text(`${totalSamples} samples`);

            legend.append("text")
                .attr("x", 0)
                .attr("y", 160)
                .style("font-size", "9px")
                .style("fill", "#666")
                .text(`Node width: ${minSampleCount}-${maxSampleCount}`);
        }

        export default { render };
        """

        _css = """
        .widget-container {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
        }

        .sample-line {
            cursor: pointer;
            transition: all 0.2s ease;
        }

        .tooltip {
            pointer-events: none;
        }

        .brush .selection {
            fill: #3498db;
            fill-opacity: 0.3;
            stroke: #2980b9;
            stroke-width: 1;
        }

        .brush .handle {
            fill: #34495e;
            fill-opacity: 0.8;
        }
        """

        # Widget traits
        nodes_data = traitlets.List(default_value=[]).tag(sync=True)
        width = traitlets.Int(default_value=1200).tag(sync=True)
        height = traitlets.Int(default_value=800).tag(sync=True)
        node_height = traitlets.Int(default_value=60).tag(sync=True)
        node_width = traitlets.Int(default_value=30).tag(sync=True)
        enable_crossing_reduction = traitlets.Bool(default_value=True).tag(
            sync=True
        )

        color_schemes = traitlets.Dict(
            default_value={
                2: "#1f77b4",
                3: "#ff7f0e",
                4: "#2ca02c",
                5: "#d62728",
                6: "#9467bd",
                7: "#8c564b",
                8: "#e377c2",
                9: "#7f7f7f",
                10: "#bcbd22",
            }
        ).tag(sync=True)

        def __init__(self, nodes_data=None, **kwargs):
            super().__init__(**kwargs)
            if nodes_data:
                self.nodes_data = nodes_data
    return (CoordinateAxesLayout,)


@app.cell
def _(CoordinateAxesLayout, sankey_data):
    nodes_data = []

    for node_name, node_info in sankey_data["nodes"].items():
        # Extract K and MC from node name (e.g., "K2_MC0")
        _k = int(node_name.split("_")[0][1:])
        _mc = int(node_name.split("_")[1][2:])

        # Collect samples with their probabilities
        _samples = []
        for _sample_id, _prob in node_info["high_samples"]:
            _samples.append({"id": _sample_id, "probability": _prob})
        nodes_data.append({"k": _k, "mc": _mc, "samples": _samples})

        for _sample_id_1, _prob_1 in node_info["medium_samples"]:
            _samples.append({"id": _sample_id_1, "probability": _prob_1})
        nodes_data.append({"k": _k, "mc": _mc, "samples": _samples})

    # Create widget with your data
    widget_test = CoordinateAxesLayout(
        nodes_data=nodes_data,
        node_height=100,
        height=1500,
        width=2000,
        enable_crossing_reduction=True,
    )
    return (widget_test,)


@app.cell
def _(widget_test):
    widget_test
    return


@app.cell
def _():
    return


if __name__ == "__main__":
    app.run()
