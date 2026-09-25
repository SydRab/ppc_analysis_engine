import os
import pandas as pd

def process_and_structure_keywords(input_csv="approved_campaign_keywords.csv", output_csv="google_ads_final_ready_import.csv"):
    if not os.path.exists(input_csv):
        print(f"Error: Input file '{input_csv}' not found.")
        return

    print(f"Loading approved keywords from {input_csv}...")
    df = pd.read_csv(input_csv)
    print(f"Loaded {len(df)} records. Processing classifications and routing paths...")

    def assign_ad_group_and_pest(keyword):
        kw = str(keyword).lower()
        if 'ant' in kw:
            return 'Ant Control', 'ant-control'
        elif 'termite' in kw:
            return 'Termite Treatment', 'termite-treatment'
        elif 'rat' in kw or 'mouse' in kw or 'mice' in kw or 'rodent' in kw:
            return 'Rodent Control', 'rodent-removal'
        elif 'bed bug' in kw:
            return 'Bed Bug Extermination', 'bed-bug-extermination'
        elif 'roach' in kw or 'cockroach' in kw:
            return 'Roach Control', 'roach-control'
        else:
            return 'General Pest Control', 'general-pest-control'

    ad_groups = []
    pest_slugs = []
    for kw in df['suggested_keyword']:
        group, slug = assign_ad_group_and_pest(kw)
        ad_groups.append(group)
        pest_slugs.append(slug)

    df['ad_group'] = ad_groups
    df['_pest_slug'] = pest_slugs

    # 1. Assign Campaign Names based on Intent / Phone Urgency
    df['campaign_name'] = df.apply(
        lambda row: 'Pest_Control_Emergency_Calls' if row.get('is_phone_intent') == True or str(row.get('bid_tier_weight')) == '3' 
        else 'Pest_Control_Commercial_Leads', axis=1
    )

    # 2. Assign Landing Page Context Route for Next.js Dynamic Routing
    def get_landing_page_mapping(row):
        intent = str(row.get('intent_type', '')).lower()
        pest_slug = row['_pest_slug']
        
        if intent == 'emergency' or row.get('is_phone_intent') == True:
            urgency_suffix = 'emergency-dispatch'
        else:
            urgency_suffix = 'service-booking'
            
        return f"/services/{pest_slug}?intent={urgency_suffix}"

    df['landing_page_route'] = df.apply(get_landing_page_mapping, axis=1)

    # Drop temporary helper column
    df = df.drop(columns=['_pest_slug'])

    # 3. Google Ads Formatting Specifications
    df['criterion_type'] = 'Phrase'  # Phrase match for controlled high-intent expansion
    df['max_cpc'] = 120.00           # Setting your max CPC bid cap

    # Export final structured dataset to a separate CSV file
    df.to_csv(output_csv, index=False)
    print(f"Successfully generated structured file with {len(df)} rows at: {output_csv}")

if __name__ == "__main__":
    process_and_structure_keywords()
