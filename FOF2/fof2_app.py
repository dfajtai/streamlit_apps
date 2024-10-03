import streamlit as st
import plotly.express as px
import pandas as pd
from pathlib import Path

# Set the title and favicon that appear in the Browser's tab bar.
st.set_page_config(
    page_title='FOF2 angio timings',
    page_icon=':earth_americas:',  # This is an emoji shortcode. Could be a URL too.
)

# -----------------------------------------------------------------------------
# Declare some useful functions.

@st.cache_data
def get_timing_data():
    """Grab timing data from a CSV file.

    This uses caching to avoid having to read the file every time. If we were
    reading from an HTTP endpoint instead of a file, it's a good idea to set
    a maximum age to the cache with the TTL argument: @st.cache_data(ttl='1d')
    """

    # Instead of a CSV on disk, you could read from an HTTP endpoint here too.
    DATA_FILENAME = Path(__file__).parent/'data/measurements.csv'
    df = pd.read_csv(DATA_FILENAME)

    # Convert columns to appropriate formats
    df['start'] = pd.to_datetime(df['start_time'])
    df['end'] = pd.to_datetime(df['end_time'])
    df['duration'] = df["end"]-df["start"]
    df['id'] = df['idx']
    # df['content'] = df.apply(lambda x: f'Specimen {x.get("specimen")}\nMeasurement {x.get("measurement")}', axis=1)

    return df[['specimen', 'start', 'end', 'duration']]

df = get_timing_data()

# Add some spacing
st.write("")
st.write("")

specimens = df['specimen'].unique()

if not len(specimens):
    st.warning("Select at least one specimen")

selected_specimens = st.multiselect(
    'Which specimen(s) would you like to review?',
    specimens,
    ['FOF2-1', 'FOF2-13', 'FOF2-25', 'FOF2-2', 'FOF2-9', 'FOF2-11', 'FOF2-28', 'FOF2-17', 'FOF2-20']
)

block_dt = st.slider(
    "Maximim distance in hours between measurements",
    min_value=0.5,max_value=12.0,value=5.0, step=0.5
)

for s in sorted(selected_specimens):
    # Filter data for the selected specimen
    filtered_df = df[df.specimen == s].copy().reset_index(drop=True)
    if len(filtered_df.index)==0:
        continue

    with st.container(border=True):
        # Initialize block column
        filtered_df['block'] = 1
        
        block = 1
        # Loop through the rows and calculate the time difference (dt)
        for index in range(1, len(filtered_df)):
            prev_end = filtered_df.iloc[index - 1]['end']
            current_start = filtered_df.iloc[index]['start']
            
            # Calculate time difference in hours between the previous row's 'end' and current row's 'start'
            dt = (current_start - prev_end) / pd.Timedelta(hours=1)  # Calculate the difference in hours
            
            # Check if the time difference is more than X hours
            if dt > block_dt:
                block += 1
            
            filtered_df.at[index, 'block'] = block

        # Plotting each block
        for b in range(1,block+1):
            sub_df = (filtered_df[filtered_df["block"] == b]).copy().sort_values(by="start").reset_index(drop=True)
            
            st.subheader(f"Specimen '{s}' [Block {b}] num of measurements: {len(sub_df.index)}", divider=True)

            # Set min and max time ranges for the block
            min_dt = sub_df['start'].min()
            max_dt = sub_df['end'].max()
            
            # Plot the timeline using Plotly Express
            fig = px.timeline(
                sub_df,
                x_start='start',
                x_end='end',
                y='specimen',
                title=f"Specimen '{s}' [Block {b}]",
                # range_x=[min_dt, max_dt]
            )

            # Update layout for better presentation
            fig.update_yaxes(categoryorder="total ascending")
            fig.update_layout(showlegend=False)

            # Display the plot in Streamlit
            st.plotly_chart(fig)
            
            with st.expander("Table"):
                st.table(sub_df)