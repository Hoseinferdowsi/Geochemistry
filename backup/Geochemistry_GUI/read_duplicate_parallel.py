import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import os
import json
import argparse
from multiprocessing import Pool, cpu_count
import sys
import codecs

# ----------------------
# Argument Parser
# ----------------------
def parse_arguments():
    parser = argparse.ArgumentParser(description='Analyze duplicate samples for analytical error.')
    parser.add_argument('--input', type=str, help='Path to input Excel file', required=True)
    parser.add_argument('--output', type=str, help='Path to output directory', required=True)
    return parser.parse_args()

# ----------------------
# Read Data
# ----------------------
def read_duplicate_data(input_file):
    excel_file = pd.ExcelFile(input_file)
    duplicate_samples = pd.read_excel(excel_file, sheet_name='Duplicate Samples')
    duplicate_data = pd.read_excel(excel_file, sheet_name='Duplicate_Data')
    return duplicate_samples, duplicate_data

# ----------------------
# Plot Functions
# ----------------------
def create_scatter_plot(orig_values, dup_values, element, mean_rpd, output_path):
    plt.figure(figsize=(10, 10))
    max_val = max(max(orig_values), max(dup_values))
    min_val = min(min(orig_values), min(dup_values))
    range_val = max_val - min_val
    plot_min = min_val - range_val * 0.05
    plot_max = max_val + range_val * 0.05
    plt.scatter(orig_values, dup_values, alpha=0.6, s=100)
    plt.plot([plot_min, plot_max], [plot_min, plot_max], 'r--', label='1:1 Line', linewidth=2)
    plt.plot([plot_min, plot_max], [plot_min*0.9, plot_max*0.9], 'k:', label='-10%')
    plt.plot([plot_min, plot_max], [plot_min*1.1, plot_max*1.1], 'k:', label='+10%')
    plt.xlabel(f'Original Sample ({element})', fontsize=12)
    plt.ylabel(f'Duplicate Sample ({element})', fontsize=12)
    plt.title(f'Original vs Duplicate Values - {element}', fontsize=14, pad=20)
    plt.legend(fontsize=10, loc='upper left', bbox_to_anchor=(0.02, 0.98))
    plt.text(0.98, 0.98, f'Mean RPD: {mean_rpd:.1f}%', transform=plt.gca().transAxes,
             bbox=dict(facecolor='white', alpha=0.8), horizontalalignment='right', verticalalignment='top', fontsize=10)
    plt.grid(True, alpha=0.3)
    plt.axis('equal')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

def create_thompson_howarth_plot(orig_values, dup_values, element, output_path):
    plt.figure(figsize=(10, 10))
    means = [(x + y) / 2 for x, y in zip(orig_values, dup_values)]
    abs_diffs = [abs(x - y) for x, y in zip(orig_values, dup_values)]
    plt.scatter(means, abs_diffs, alpha=0.6, s=100)
    z = np.polyfit(means, abs_diffs, 1)
    p = np.poly1d(z)
    x_range = np.linspace(min(means), max(means), 100)
    reg_line = p(x_range)
    plt.plot(x_range, reg_line, 'k-', label='Regression line', linewidth=1.5)
    for conf_level, multiplier in {0.90: 2.32617, 0.99: 3.64277}.items():
        conf_line = reg_line * multiplier
        plt.plot(x_range, conf_line, linestyle='--', label=f'{int(conf_level*100)}% Confidence Limit')
    plt.xlabel(f'Mean Concentration ({element})', fontsize=12)
    plt.ylabel('Absolute Difference', fontsize=12)
    plt.title(f'Thompson-Howarth Plot - {element}', fontsize=14, pad=20)
    plt.legend(fontsize=10)
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

def create_log_thompson_howarth_plot(means, abs_diffs, element, mean_rpd, output_path):
    """Create Thompson-Howarth plot with logarithmic scales"""
    plt.figure(figsize=(10, 10))
    
    # Filter out zero values
    valid_indices = [i for i, (m, d) in enumerate(zip(means, abs_diffs)) if m > 0 and d > 0]
    if not valid_indices:
        print(f"Warning: No valid (non-zero) data points for {element}")
        plt.close()
        return
        
    valid_means = [means[i] for i in valid_indices]
    valid_diffs = [abs_diffs[i] for i in valid_indices]
    
    # Calculate axis limits
    min_mean = np.min(valid_means)
    max_mean = np.max(valid_means)
    min_diff = np.min(valid_diffs)
    max_diff = np.max(valid_diffs)
    
    # Set default x-axis limits
    x_min = 0.1
    x_max = 10000
    
    # Adjust x-axis limits if data falls outside the range
    if min_mean < x_min:
        x_min = 10 ** np.floor(np.log10(min_mean))
    if max_mean > x_max:
        x_max = 10 ** np.ceil(np.log10(max_mean))
    
    # Set default y-axis limits
    y_min = 0.01
    y_max = 1000
    
    # Adjust y-axis limits if data falls outside the range
    if min_diff < y_min:
        y_min = 10 ** np.floor(np.log10(min_diff))
    if max_diff > y_max:
        y_max = 10 ** np.ceil(np.log10(max_diff))
    
    # Create scatter plot
    plt.scatter(valid_means, valid_diffs, alpha=0.6, s=100)
    
    # Create x values for plotting error lines
    x_reg = np.logspace(np.log10(x_min), np.log10(x_max), 100)
    
    # Add 10% and 20% error lines
    plt.plot(x_reg, x_reg * 0.1, 'g:', label='10% Error', linewidth=1.5)
    plt.plot(x_reg, x_reg * 0.2, 'b:', label='20% Error', linewidth=1.5)
    
    plt.xscale('log')
    plt.yscale('log')
    
    plt.grid(True, which="both", ls="-", alpha=0.2)
    plt.xlabel(f'Mean Concentration ({element})', fontsize=12)
    plt.ylabel('Absolute Difference', fontsize=12)
    
    # Add text box with statistics at top left
    stats_text = f'Mean RPD: {mean_rpd:.1f}%'
    plt.text(0.02, 0.98, stats_text, 
            transform=plt.gca().transAxes,
            bbox=dict(facecolor='white', alpha=0.8),
            verticalalignment='top',
            fontsize=10)
    
    # Move legend to the left side below Mean RPD text box
    plt.legend(loc='upper left', bbox_to_anchor=(0.02, 0.90),
              fontsize=10, framealpha=0.8)
    
    # Set axis limits
    plt.xlim(x_min, x_max)
    plt.ylim(y_min, y_max)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

def create_comparison_plot(orig_values, dup_values, element, output_path):
    plt.figure(figsize=(12, 8))
    sample_indices = range(1, len(orig_values) + 1)
    plt.plot(sample_indices, orig_values, 'b-o', label='Original Sample', linewidth=2, markersize=8, alpha=0.7)
    plt.plot(sample_indices, dup_values, 'r--o', label='Duplicate Sample', linewidth=2, markersize=8, alpha=0.7)
    plt.xlabel('Sample Pair Number', fontsize=12)
    plt.ylabel(f'Concentration ({element})', fontsize=12)
    plt.title(f'Original vs Duplicate Values - {element}', fontsize=14, pad=20)
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

def categorize_quality(row):
    if row['Percent_Above_20pct'] <= 1 and row['Percentage_Above_10'] <= 10:
        return 'خوب'
    elif row['Percent_Above_20pct'] <= 5 and row['Percentage_Above_10'] <= 30:
        return 'قابل قبول'
    else:
        return 'ضعیف'

# ----------------------
# Core Processing Function
# ----------------------
def process_element(args):
    element, duplicate_samples, duplicate_data, output_dirs = args
    orig_values = []
    dup_values = []
    for _, row in duplicate_samples.iterrows():
        orig_sample = row['Sample_ID']
        dup_sample = row['Duplicated_Sample_ID']
        orig_value = duplicate_data[duplicate_data['Sample_ID'] == orig_sample][element].iloc[0]
        dup_value = duplicate_data[duplicate_data['Sample_ID'] == dup_sample][element].iloc[0]
        orig_values.append(orig_value)
        dup_values.append(dup_value)
    rpd_values = [abs(o - d) / ((o + d) / 2) * 100 if (o + d) != 0 else 0 for o, d in zip(orig_values, dup_values)]
    mean_rpd = np.mean(rpd_values)
    abs_diffs = [abs(o - d) for o, d in zip(orig_values, dup_values)]
    means = [(o + d) / 2 for o, d in zip(orig_values, dup_values)]

    create_scatter_plot(orig_values, dup_values, element, mean_rpd, output_dirs['scatter_plots'] / f'{element}_scatter.png')
    #create_thompson_howarth_plot(orig_values, dup_values, element, output_dirs['thompson_howarth_plots'] / f'{element}_thompson_howarth.png')
    create_log_thompson_howarth_plot(means, abs_diffs, element, mean_rpd, output_dirs['log_thompson_howarth_plots'] / f'{element}_log_thompson_howarth.png')
    create_comparison_plot(orig_values, dup_values, element, output_dirs['comparison_plots'] / f'{element}_comparison.png')

    return {'Element': element, 
            'Mean_RPD': mean_rpd,
            'Median_RPD': np.median(rpd_values),
            'Q1_RPD': np.percentile(rpd_values, 25),  # Add this line
            'Q3_RPD': np.percentile(rpd_values, 75),  # Add this line
            'Std_RPD': np.std(rpd_values),
            'Min_RPD': np.min(rpd_values),
            'Max_RPD': np.max(rpd_values),
            'Samples_Above_20pct': sum(1 for r in rpd_values if r > 20),
            'Percent_Above_20pct': (sum(1 for r in rpd_values if r > 20) / len(rpd_values)) * 100,
            'Points_Above_10': sum(1 for r in rpd_values if r > 10),
            'Percentage_Above_10': (sum(1 for r in rpd_values if r > 10) / len(rpd_values)) * 100,
            'Original_Mean': np.mean(orig_values),
            'Duplicate_Mean': np.mean(dup_values),
            'Original_Std': np.std(orig_values),
            'Duplicate_Std': np.std(dup_values),
            'Mean_Abs_Diff': np.mean(abs_diffs),
            'Abs_Diff_Std': np.std(abs_diffs)           
    }

def create_summary_plots(error_df, output_dir):
    """Create summary visualizations"""
    # Sort elements by mean RPD
    error_df_sorted = error_df.sort_values('Mean_RPD', ascending=True)
    
    # 1. Bar plot of mean RPD for each element
    plt.figure(figsize=(15, 8))
    bars = plt.bar(range(len(error_df_sorted)), error_df_sorted['Mean_RPD'])
    
    # Color bars based on RPD value
    for i, bar in enumerate(bars):
        if error_df_sorted['Mean_RPD'].iloc[i] > 20:
            bar.set_color('red')
        elif error_df_sorted['Mean_RPD'].iloc[i] > 10:
            bar.set_color('orange')
        else:
            bar.set_color('green')
    
    plt.axhline(y=20, color='r', linestyle='--', label='20% Threshold')
    plt.axhline(y=10, color='orange', linestyle='--', label='10% Threshold')
    plt.xticks(range(len(error_df_sorted)), error_df_sorted['Element'], rotation=90)
    plt.xlabel('Elements')
    plt.ylabel('Mean RPD (%)')
    plt.title('Mean Relative Percent Difference (RPD) by Element')
    plt.legend()
    plt.grid(True, axis='y')
    plt.tight_layout()
    plt.savefig(output_dir / 'mean_rpd_by_element.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # 2. Box plot for RPD distribution using Q1, Q3, and Median
    plt.figure(figsize=(15, 8))
    box_data = []
    for _, row in error_df_sorted.iterrows():
        box_data.append([
            row['Q1_RPD'],
            row['Median_RPD'],
            row['Q3_RPD']
        ])
    
    plt.boxplot(box_data, labels=error_df_sorted['Element'])
    plt.axhline(y=20, color='r', linestyle='--', label='20% Threshold')
    plt.axhline(y=10, color='orange', linestyle='--', label='10% Threshold')
    plt.xticks(rotation=90)
    plt.xlabel('Elements')
    plt.ylabel('RPD (%)')
    plt.title('Distribution of RPD Values by Element')
    plt.legend()
    plt.grid(True, axis='y')
    plt.tight_layout()
    plt.savefig(output_dir / 'rpd_distribution.png', dpi=300, bbox_inches='tight')
    plt.close()

# ----------------------
# Main Analysis
# ----------------------
def main():
    args = parse_arguments()
    global output_dir
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)

    #
    output_dirs = {
        'scatter_plots': output_dir / 'scatter_plots',
        'comparison_plots': output_dir / 'comparison_plots',
        'thompson_howarth_plots': output_dir / 'thompson_howarth_plots',
        'log_thompson_howarth_plots': output_dir / 'log_thompson_howarth_plots',
        'output_dir': output_dir
    }
    for dir_path in output_dirs.values():
        dir_path.mkdir(exist_ok=True)

    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)

    print("Reading duplicate samples file...")
    duplicate_samples, duplicate_data = read_duplicate_data(args.input)

    print("\nProcessing elements...")
    element_columns = [col for col in duplicate_data.columns if col != 'Sample_ID']
    num_cores = cpu_count()

    with Pool(num_cores) as pool:
        results = pool.map(
            process_element,
            [(element, duplicate_samples, duplicate_data, output_dirs) for element in element_columns]
        )

    results_df = pd.DataFrame(results)
    results_df['Quality_Category'] = results_df.apply(categorize_quality, axis=1)
    #add summary plots
    create_summary_plots(results_df,output_dir)

    results_df.to_excel(output_dir / 'analytical_error_analysis.xlsx', index=False)

    quality_summary = results_df.groupby(
        pd.cut(results_df['Mean_RPD'], bins=[-np.inf, 10, 20, np.inf], labels=['خوب', 'قابل قبول', 'ضعیف']),
        observed=True
    )['Element'].agg(list).reset_index()
    top_elements = results_df.nlargest(10, 'Mean_RPD')

    results_json = {
        'stats': results_df.to_dict('records'),
        'quality_summary': quality_summary.to_dict('records'),
        'top_elements': top_elements.to_dict('records')
    }

    with open(output_dir / 'results.json', 'w', encoding='utf-8') as f:
        json.dump(results_json, f, ensure_ascii=False, indent=4)

    print("\nAnalysis complete. Results saved.")

if __name__ == "__main__":
    main()
