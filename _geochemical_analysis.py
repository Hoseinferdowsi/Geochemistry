import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
import os

# Set plot style
plt.style.use('seaborn')
sns.set_palette("husl")

# Create output directory if it doesn't exist
output_dir = Path('output')
output_dir.mkdir(exist_ok=True)

def read_data():
    """Read the geochemical and duplicate samples data"""
    # Read the main geochemical data
    print("Reading Au_ICP_2.xlsx...")
    geochem_data = pd.read_excel('Data/Au_ICP_2.xlsx')
    print("\nFirst 5 rows of Au_ICP_2.xlsx:")
    print(geochem_data.head())
    print("\nColumns in Au_ICP_2.xlsx:")
    print(geochem_data.columns.tolist())
    
    # Read the duplicate samples data
    print("\nReading Duplicate_SAmples.xlsx...")
    duplicate_data = pd.read_excel('Data/Duplicate_SAmples.xlsx')
    print("\nFirst 5 rows of Duplicate_SAmples.xlsx:")
    print(duplicate_data.head())
    print("\nColumns in Duplicate_SAmples.xlsx:")
    print(duplicate_data.columns.tolist())
    
    # Print sample IDs from both files for comparison
    print("\nFirst 5 Sample IDs from Au_ICP_2.xlsx:")
    print(geochem_data['Sample_ID'].head())
    print("\nFirst 5 Original and Duplicate samples from Duplicate_SAmples.xlsx:")
    print(duplicate_data[['Sample_ID', 'Duplicated_Sample_ID']].head())
    
    return geochem_data, duplicate_data

def calculate_precision_metrics(original_samples, duplicate_samples):
    """Calculate precision metrics for duplicate samples"""
    # Calculate relative percent difference (RPD)
    rpd = np.abs(original_samples - duplicate_samples) / ((original_samples + duplicate_samples) / 2) * 100
    
    # Calculate basic statistics
    mean_rpd = rpd.mean()
    median_rpd = rpd.median()
    std_rpd = rpd.std()
    
    # Calculate HARD (Half Absolute Relative Difference)
    hard = rpd / 2
    mean_hard = hard.mean()
    
    return {
        'RPD': rpd,
        'Mean_RPD': mean_rpd,
        'Median_RPD': median_rpd,
        'Std_RPD': std_rpd,
        'Mean_HARD': mean_hard
    }

def create_precision_plots(original_samples, duplicate_samples, element_name):
    """Create scatter and QQ plots for precision analysis"""
    # Create scatter plot
    plt.figure(figsize=(10, 6))
    plt.scatter(original_samples, duplicate_samples, alpha=0.5)
    
    # Add 1:1 line
    max_val = max(original_samples.max(), duplicate_samples.max())
    min_val = min(original_samples.min(), duplicate_samples.min())
    plt.plot([min_val, max_val], [min_val, max_val], 'r--', label='1:1 Line')
    
    plt.xlabel(f'Original Samples {element_name}')
    plt.ylabel(f'Duplicate Samples {element_name}')
    plt.title(f'Original vs Duplicate Samples - {element_name}')
    plt.legend()
    plt.grid(True)
    plt.savefig(output_dir / f'scatter_plot_{element_name}.png', dpi=300, bbox_inches='tight')
    plt.close()
    
    # Create RPD plot
    rpd = calculate_precision_metrics(original_samples, duplicate_samples)['RPD']
    plt.figure(figsize=(10, 6))
    plt.hist(rpd, bins=20, alpha=0.7)
    plt.axvline(rpd.mean(), color='r', linestyle='--', label=f'Mean RPD: {rpd.mean():.2f}%')
    plt.xlabel('Relative Percent Difference (%)')
    plt.ylabel('Frequency')
    plt.title(f'Distribution of RPD - {element_name}')
    plt.legend()
    plt.grid(True)
    plt.savefig(output_dir / f'rpd_hist_{element_name}.png', dpi=300, bbox_inches='tight')
    plt.close()

def analyze_duplicates(geochem_data, duplicate_data):
    """Analyze duplicate samples and calculate precision metrics"""
    # Initialize results dictionary
    results = {}
    
    # Get numeric columns (excluding coordinates)
    numeric_columns = geochem_data.select_dtypes(include=[np.number]).columns
    numeric_columns = [col for col in numeric_columns if col not in ['X', 'Y']]
    
    # Calculate precision metrics for each element
    for element in numeric_columns:
        original_values = []
        duplicate_values = []
        
        for _, row in duplicate_data.iterrows():
            orig_sample = row['Sample_ID']  # Original sample number
            dup_sample = row['Duplicated_Sample_ID']  # Duplicate sample number
            
            # Get values for original and duplicate samples
            orig_value = geochem_data.loc[geochem_data['Sample_ID'] == orig_sample, element].values
            dup_value = geochem_data.loc[geochem_data['Sample_ID'] == dup_sample, element].values
            
            if len(orig_value) > 0 and len(dup_value) > 0:
                original_values.append(orig_value[0])
                duplicate_values.append(dup_value[0])
        
        if original_values and duplicate_values:
            original_values = np.array(original_values)
            duplicate_values = np.array(duplicate_values)
            
            # Calculate precision metrics
            metrics = calculate_precision_metrics(original_values, duplicate_values)
            results[element] = metrics
            
            # Create plots
            create_precision_plots(original_values, duplicate_values, element)
    
    return results

def export_results(results):
    """Export analysis results to Excel"""
    # Create summary dataframe
    summary_data = {
        'Element': [],
        'Mean_RPD': [],
        'Median_RPD': [],
        'Std_RPD': [],
        'Mean_HARD': []
    }
    
    for element, metrics in results.items():
        summary_data['Element'].append(element)
        summary_data['Mean_RPD'].append(metrics['Mean_RPD'])
        summary_data['Median_RPD'].append(metrics['Median_RPD'])
        summary_data['Std_RPD'].append(metrics['Std_RPD'])
        summary_data['Mean_HARD'].append(metrics['Mean_HARD'])
    
    summary_df = pd.DataFrame(summary_data)
    
    # Sort by Mean RPD to identify elements with highest variability
    summary_df = summary_df.sort_values('Mean_RPD', ascending=False)
    
    # Export to Excel
    with pd.ExcelWriter(output_dir / 'precision_analysis_results.xlsx') as writer:
        summary_df.to_excel(writer, sheet_name='Summary', index=False)

def main():
    # Read and display data
    print("Checking data files...")
    geochem_data, duplicate_data = read_data()
    
    # Check for any missing values
    print("\nChecking for missing values in Au_ICP_2.xlsx:")
    print(geochem_data.isnull().sum())
    
    print("\nChecking for missing values in Duplicate_SAmples.xlsx:")
    print(duplicate_data.isnull().sum())
    
    # Check data types
    print("\nData types in Au_ICP_2.xlsx:")
    print(geochem_data.dtypes)
    
    print("\nData types in Duplicate_SAmples.xlsx:")
    print(duplicate_data.dtypes)

    # Analyze duplicates
    print("Analyzing duplicate samples...")
    results = analyze_duplicates(geochem_data, duplicate_data)
    
    # Export results
    print("Exporting results...")
    export_results(results)
    
    print("Analysis complete. Results have been saved to the 'output' directory.")
    print("\nSummary of files generated:")
    print("1. precision_analysis_results.xlsx - Contains statistical summary of precision metrics")
    print("2. Scatter plots for each element (scatter_plot_*.png)")
    print("3. RPD distribution histograms for each element (rpd_hist_*.png)")

if __name__ == "__main__":
    main() 