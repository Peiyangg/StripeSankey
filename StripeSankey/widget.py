import anywidget
import traitlets

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