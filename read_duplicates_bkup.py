import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import os
import json
import argparse

def parse_arguments():
    parser = argparse.ArgumentParser(description='Analyze duplicate samples for analytical error.')
    parser.add_argument('--input', type=str, help='Path to input Excel file', required=True)
    parser.add_argument('--output', type=str, help='Path to output directory', required=True)
    return parser.parse_args()

def read_duplicate_data(input_file):
    """Read both sheets of the duplicate samples Excel file"""
    # Read the Excel file with all sheets
    excel_file = pd.ExcelFile(input_file)
    
    # Read each sheet into a separate DataFrame
    duplicate_samples = pd.read_excel(excel_file, sheet_name='Duplicate Samples')
    duplicate_data = pd.read_excel(excel_file, sheet_name='Duplicate_Data')
    
    return duplicate_samples, duplicate_data

def create_scatter_plot(orig_values, dup_values, element, mean_rpd, output_path):
    """Create scatter plot for a single element"""
    plt.figure(figsize=(10, 10))
    
    # Calculate axis limits
    max_val = max(max(orig_values), max(dup_values))
    min_val = min(min(orig_values), min(dup_values))
    range_val = max_val - min_val
    plot_min = min_val - range_val * 0.05
    plot_max = max_val + range_val * 0.05
    
    # Plot scatter and 1:1 line
    plt.scatter(orig_values, dup_values, alpha=0.6, s=100)  # Increased point size
    plt.plot([plot_min, plot_max], [plot_min, plot_max], 'r--', label='1:1 Line', linewidth=2)
    
    # Add 10% error lines
    plt.plot([plot_min, plot_max], [plot_min*0.9, plot_max*0.9], 'k:', label='-10%')
    plt.plot([plot_min, plot_max], [plot_min*1.1, plot_max*1.1], 'k:', label='+10%')
    
    plt.xlabel(f'Original Sample ({element})', fontsize=12)
    plt.ylabel(f'Duplicate Sample ({element})', fontsize=12)
    plt.title(f'Original vs Duplicate Values - {element}', fontsize=14, pad=20)
    
    # Add legend to the upper left side
    plt.legend(fontsize=10, loc='upper left', bbox_to_anchor=(0.02, 0.98))
    
    # Add mean RPD text to the upper right side
    plt.text(0.98, 0.98, f'Mean RPD: {mean_rpd:.1f}%', 
             transform=plt.gca().transAxes,
             bbox=dict(facecolor='white', alpha=0.8),
             horizontalalignment='right',
             verticalalignment='top',
             fontsize=10)
    
    plt.grid(True, alpha=0.3)
    plt.axis('equal')
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

def create_thompson_howarth_plot(orig_values, dup_values, element, output_path):
    """Create Thompson-Howarth plot for precision analysis"""
    plt.figure(figsize=(10, 10))
    
    # Calculate mean and absolute difference for each pair
    means = [(x + y) / 2 for x, y in zip(orig_values, dup_values)]
    abs_diffs = [abs(x - y) for x, y in zip(orig_values, dup_values)]
    
    # Create the plot
    plt.scatter(means, abs_diffs, alpha=0.6, s=100)
    
    # Calculate regression line
    z = np.polyfit(means, abs_diffs, 1)
    p = np.poly1d(z)
    x_range = np.linspace(min(means), max(means), 100)
    
    # Add regression line
    reg_line = p(x_range)
    plt.plot(x_range, reg_line, 'k-', label='Regression line', linewidth=1.5)
    
    # Calculate and plot confidence limits using regression line
    conf_multipliers = {
        0.90: 2.32617,  # 90% confidence limit multiplier
        0.99: 3.64277   # 99% confidence limit multiplier
    }
    
    colors = {0.90: 'g', 0.99: 'r'}
    styles = {0.90: '--', 0.99: '--'}
    
    # Plot confidence limits
    for conf_level, multiplier in conf_multipliers.items():
        conf_line = reg_line * multiplier
        plt.plot(x_range, conf_line, color=colors[conf_level], linestyle=styles[conf_level],
                label=f'{int(conf_level*100)}% Confidence Limit')
    
    # Set y-axis limits to show confidence limits clearly
    y_vals = abs_diffs + list(reg_line * conf_multipliers[0.99])  # Include confidence limit values
    y_max = max(y_vals) * 1.1  # Add 10% margin
    y_min = 0  # Start from 0
    plt.ylim(y_min, y_max)
    
    plt.xlabel(f'Mean Concentration ({element})', fontsize=12)
    plt.ylabel('Absolute Difference', fontsize=12)
    plt.title(f'Thompson-Howarth Plot - {element}', fontsize=14, pad=20)
    
    # Calculate points above 99% limit
    points_above_99 = sum(1 for i, y in enumerate(abs_diffs) if y > p(means[i]) * conf_multipliers[0.99])
    
    # Add statistics text box
    stats_text = (f'Number of pairs: {len(means)}\n'
                 f'Mean abs. diff: {np.mean(abs_diffs):.2f}\n'
                 f'Regression equation: y = {z[0]:.2e}x + {z[1]:.2e}\n'
                 f'Points above 99% limit: {points_above_99}')
    plt.text(0.05, 0.95, stats_text, transform=plt.gca().transAxes,
             bbox=dict(facecolor='white', alpha=0.8),
             verticalalignment='top', fontsize=10)
    
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
    """Create comparison plot showing original and duplicate values for each sample"""
    plt.figure(figsize=(12, 8))
    
    # Create sample indices for x-axis
    sample_indices = range(1, len(orig_values) + 1)
    
    # Plot both lines
    plt.plot(sample_indices, orig_values, 'b-o', label='Original Sample', linewidth=2, markersize=8, alpha=0.7)
    plt.plot(sample_indices, dup_values, 'r--o', label='Duplicate Sample', linewidth=2, markersize=8, alpha=0.7)
    
    # Calculate statistics
    mean_diff = np.mean([abs(o - d) for o, d in zip(orig_values, dup_values)])
    mean_rpd = np.mean([abs(o - d) / ((o + d) / 2) * 100 for o, d in zip(orig_values, dup_values)])
    
    # Add statistics text box
    stats_text = (f'Mean Difference: {mean_diff:.2f}\n'
                 f'Mean RPD: {mean_rpd:.1f}%')
    plt.text(0.02, 0.98, stats_text,
             transform=plt.gca().transAxes,
             bbox=dict(facecolor='white', alpha=0.8),
             verticalalignment='top',
             fontsize=10)
    
    plt.xlabel('Sample Pair Number', fontsize=12)
    plt.ylabel(f'Concentration ({element})', fontsize=12)
    plt.title(f'Original vs Duplicate Values - {element}', fontsize=14, pad=20)
    
    # Set x-axis to show integer values
    plt.xticks(sample_indices)
    
    # Add grid
    plt.grid(True, alpha=0.3)
    
    # Add legend
    plt.legend(loc='upper right', bbox_to_anchor=(0.98, 0.98),
              fontsize=10, framealpha=0.8)
    
    plt.tight_layout()
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()

def calculate_analytical_error(duplicate_samples, duplicate_data, output_dirs):
    """Calculate analytical error for each element"""
    # Create output directories if they don't exist
    for dir_path in output_dirs.values():
        os.makedirs(dir_path, exist_ok=True)
    
    # Get all element columns (excluding Sample_ID)
    element_columns = [col for col in duplicate_data.columns if col != 'Sample_ID']
    
    # Initialize lists to store results
    results = []
    
    # Process each element
    for element in element_columns:
        # Get original and duplicate values for this element
        orig_values = []
        dup_values = []
        
        for _, row in duplicate_samples.iterrows():
            orig_sample = row['Sample_ID']
            dup_sample = row['Duplicated_Sample_ID']
            
            orig_value = duplicate_data[duplicate_data['Sample_ID'] == orig_sample][element].iloc[0]
            dup_value = duplicate_data[duplicate_data['Sample_ID'] == dup_sample][element].iloc[0]
            
            orig_values.append(orig_value)
            dup_values.append(dup_value)
        
        # Calculate RPD for each pair
        rpd_values = []
        for o, d in zip(orig_values, dup_values):
            if (o + d) / 2 != 0:  # Avoid division by zero
                rpd = abs(o - d) / ((o + d) / 2) * 100
                rpd_values.append(rpd)
            else:
                rpd_values.append(0)
        
        # Calculate statistics
        mean_rpd = np.mean(rpd_values)
        std_rpd = np.std(rpd_values)
        median_rpd = np.median(rpd_values)
        min_rpd = np.min(rpd_values)
        max_rpd = np.max(rpd_values)
        q1_rpd = np.percentile(rpd_values, 25)
        q3_rpd = np.percentile(rpd_values, 75)
        iqr_rpd = q3_rpd - q1_rpd
        
        # Calculate number and percentage of points with error > 10% and > 20%
        points_above_10 = sum(1 for rpd in rpd_values if rpd > 10)
        percentage_above_10 = (points_above_10 / len(rpd_values)) * 100
        points_above_20 = sum(1 for rpd in rpd_values if rpd > 20)
        percentage_above_20 = (points_above_20 / len(rpd_values)) * 100
        
        # Calculate means and standard deviations
        orig_mean = np.mean(orig_values)
        dup_mean = np.mean(dup_values)
        orig_std = np.std(orig_values)
        dup_std = np.std(dup_values)
        
        # Calculate absolute differences
        abs_diffs = [abs(o - d) for o, d in zip(orig_values, dup_values)]
        mean_abs_diff = np.mean(abs_diffs)
        abs_diff_std = np.std(abs_diffs)
        
        # Determine quality category based on new criteria
        if percentage_above_20 <= 1 and percentage_above_10 <= 10:
            quality = 'خوب'
        elif percentage_above_20 <= 5 and percentage_above_10 <= 30:
            quality = 'قابل قبول'
        else:
            quality = 'ضعیف'
        
        # Store results
        results.append({
            'Element': element,
            'Mean_RPD': mean_rpd,
            'Median_RPD': median_rpd,
            'Min_RPD': min_rpd,
            'Max_RPD': max_rpd,
            'Std_RPD': std_rpd,
            'Q1_RPD': q1_rpd,
            'Q3_RPD': q3_rpd,
            'IQR_RPD': iqr_rpd,
            'Samples_Above_20pct': points_above_20,
            'Percent_Above_20pct': percentage_above_20,
            'Points_Above_10': points_above_10,
            'Percentage_Above_10': percentage_above_10,
            'Original_Mean': orig_mean,
            'Duplicate_Mean': dup_mean,
            'Original_Std': orig_std,
            'Duplicate_Std': dup_std,
            'Mean_Abs_Diff': mean_abs_diff,
            'Abs_Diff_Std': abs_diff_std,
            'Quality_Category': quality
        })
        
        # Create plots
        create_scatter_plot(orig_values, dup_values, element, mean_rpd, 
                          os.path.join(output_dirs['scatter_plots'], f'{element}_scatter.png'))
        
        create_thompson_howarth_plot(orig_values, dup_values, element,
                                   os.path.join(output_dirs['thompson_howarth_plots'], f'{element}_thompson_howarth.png'))
        
        # Calculate means and differences for log plot
        means = [(x + y) / 2 for x, y in zip(orig_values, dup_values)]
        abs_diffs = [abs(x - y) for x, y in zip(orig_values, dup_values)]
        create_log_thompson_howarth_plot(means, abs_diffs, element, mean_rpd,
                                       os.path.join(output_dirs['log_thompson_howarth_plots'], f'{element}_log_thompson_howarth.png'))
        
        create_comparison_plot(orig_values, dup_values, element,
                             os.path.join(output_dirs['comparison_plots'], f'{element}_comparison.png'))
    
    # Create DataFrame from results
    results_df = pd.DataFrame(results)
    
    # Save results to Excel
    results_df.to_excel(os.path.join(output_dirs['output_dir'], 'analytical_error_analysis.xlsx'), index=False)
    
    # Create summary plots
    create_summary_plots(results_df, output_dirs['output_dir'])
    
    return results_df

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

def export_results(error_df):
    """Export analysis results to Excel"""
    # Sort by Mean RPD for better readability
    error_df_sorted = error_df.sort_values('Mean_RPD', ascending=False)
    
    # Add quality categories
    error_df_sorted['Quality_Category'] = pd.cut(
        error_df_sorted['Mean_RPD'],
        bins=[-np.inf, 10, 20, np.inf],
        labels=['خوب', 'قابل قبول', 'ضعیف']
    )
    
    # Export to Excel with multiple sheets
    with pd.ExcelWriter(output_dir / 'analytical_error_analysis.xlsx') as writer:
        # Full statistics
        error_df_sorted.to_excel(writer, sheet_name='RPD_Statistics', index=False)
        
        # Summary by quality category
        quality_summary = error_df_sorted.groupby('Quality_Category', observed=True)['Element'].agg(list).reset_index()
        quality_summary.to_excel(writer, sheet_name='Quality_Summary', index=False)
    
    return error_df_sorted, quality_summary

def main():
    # Parse command line arguments
    args = parse_arguments()
    
    # Set output directory
    global output_dir
    output_dir = Path(args.output)
    output_dir.mkdir(exist_ok=True)
    
    # Create subdirectories
    output_dirs = {
        'scatter_plots': output_dir / 'scatter_plots',
        'comparison_plots': output_dir / 'comparison_plots',
        'thompson_howarth_plots': output_dir / 'thompson_howarth_plots',
        'log_thompson_howarth_plots': output_dir / 'log_thompson_howarth_plots',
        'output_dir': output_dir
    }
    
    for dir_path in output_dirs.values():
        dir_path.mkdir(exist_ok=True)
    
    # Set console encoding to UTF-8
    import sys
    import codecs
    sys.stdout = codecs.getwriter('utf-8')(sys.stdout.buffer)
    
    print("Reading duplicate samples file...")
    duplicate_samples, duplicate_data = read_duplicate_data(args.input)
    
    print("\nCalculating analytical error and creating plots...")
    error_df = calculate_analytical_error(duplicate_samples, duplicate_data, output_dirs)
    
    print("\nCreating summary plots...")
    create_summary_plots(error_df, output_dirs['output_dir'])
    
    print("\nExporting results...")
    error_df_sorted, quality_summary = export_results(error_df)
    
    print("\nAnalysis complete. Results have been saved to the output directory:")
    print(f"1. {output_dir}/analytical_error_analysis.xlsx - Detailed error statistics and quality categories")
    print(f"2. {output_dir}/mean_rpd_by_element.png - Bar plot of mean RPD by element")
    print(f"3. {output_dir}/rpd_distribution.png - Box plot showing RPD distribution for each element")
    print(f"4. {output_dirs['scatter_plots']}/ - Directory containing scatter plots for all elements")
    print(f"5. {output_dirs['comparison_plots']}/ - Directory containing comparison plots for all elements")
    print(f"6. {output_dirs['log_thompson_howarth_plots']}/ - Directory containing logarithmic Thompson-Howarth plots")
    
    # Print summary statistics
    print("\nخلاصه دسته‌بندی کیفیت:")
    for category in ['خوب', 'قابل قبول', 'ضعیف']:
        count = len(error_df_sorted[error_df_sorted['Quality_Category'] == category])
        print(f"{category}: {count} عنصر")
    
    print("\nعناصر با بیشترین RPD:")
    top_elements = error_df_sorted.nlargest(10, 'Mean_RPD')
    for _, row in top_elements.iterrows():
        print(f"{row['Element']}: {row['Mean_RPD']:.2f}% (±{row['Std_RPD']:.2f}%) - {row['Percentage_Above_10']:.1f}% samples above 10% RPD")

    # Save results to JSON with proper encoding
    results = {
        'stats': error_df_sorted.to_dict('records'),
        'quality_summary': quality_summary.to_dict('records'),
        'top_elements': top_elements.to_dict('records')
    }
    
    with open(output_dir / 'results.json', 'w', encoding='utf-8') as f:
        json.dump(results, f, ensure_ascii=False, indent=4)

if __name__ == "__main__":
    main() 