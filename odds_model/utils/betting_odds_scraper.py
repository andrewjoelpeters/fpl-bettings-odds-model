import requests
import os
from bs4 import BeautifulSoup
import pandas as pd
from selenium import webdriver
from selenium.webdriver.common.by import By
import time
from datetime import date
import json
import pickle

def get_match_slugs():
    url = 'https://www.bettingodds.com/football/premier-league'
    page = requests.get(url)
    soup = BeautifulSoup(page.content, 'html.parser')

    match_slugs = [a['href']  for a in soup.find_all('a', class_='oddsstats', href=True)]
    print(f'Retrieveed {len(match_slugs)} total matches.')
    return match_slugs

def close_popup_if_exists(driver):
    try: 
        driver.find_element('class name', 'close-modal').click()
    except: 
        pass
    
def close_cookies_wrapper_if_exists(driver):
    try:
        driver.find_element('class name', 'accept-cross-button cookie-button-link').click()
    except:
        pass
    
def get_match_info(driver, match_slug):
    match_url = 'https://www.bettingodds.com' + match_slug
    driver.get(match_url)
    #driver.execute_script("document.body.style.zoom='30%'")
    
    # Let page fully load
    time.sleep(.25)

    # Close Pop-up if Exists and Navigate to Correct Table
    close_popup_if_exists(driver)
    close_cookies_wrapper_if_exists(driver)
    
    #After Closing Pop-up, again give time for page load
    time.sleep(2)
    
    # Get Names of Teams Playing Match and Position of Each Table on Page.
    team_names = [t.text for t in driver.find_elements('class name', 'team-name')]
    match_date = driver.find_element('class name', 'match-date').text
    print(f'{team_names}: {match_date}')
    
    tables_names = {tn.text: idx for idx, tn in enumerate(driver.find_elements('class name', 'mtb-header'))}
    
    return driver, tables_names, team_names, match_date

def get_scoreline_odds(driver, tables_names, match_date, team_names):
    score_idx = tables_names['Correct Score']
    
    # Click on the dropdown to expand the correct score block, and load the score data elements
    driver.execute_script("arguments[0].scrollIntoView();", driver.find_elements('class name', 'mtb-header')[score_idx])
    driver.find_elements('class name', 'mtb-header')[score_idx].click()
    score_data = driver.find_elements('class name', 'mtb-content')[score_idx]
    
    # Scroll to the "view more" button and click it, so all data is available
    driver.execute_script("arguments[0].scrollIntoView();", score_data.find_element('class name', 'ot-view-more'))
    score_data.find_element('class name', 'ot-view-more').click()
    
    # Loop through each row of scoreline data to build table.
    print('** collecting score data')
    home_score = []
    away_score = []
    odds = []
    for row in score_data.find_elements('class name', 'results-row'):
        odds_grid = row.find_element('class name', 'grid-odds-list').find_elements('tag name', 'li')
        for odds_val in odds_grid:
            if odds_val.get_attribute('data-runner'):
                scoreline = odds_val.get_attribute('data-runner').split('-')
                home_score.append(scoreline[0])
                away_score.append(scoreline[1])
                odds.append(odds_val.get_attribute('data-decimal'))
                
    # Make Dataframe with Resulting Data
    df = pd.DataFrame(zip(home_score, away_score, odds), columns=['home_score', 'away_score', 'odds'], dtype='float')
    df['home_team'] = team_names[0]
    df['away_team'] = team_names[1]
    df['match_date'] = match_date
    
    #odds of 0 don't make sense, remove
    df = df[df.odds > 0]
    
    df = (df
      .groupby(['home_team', 'away_team', 'match_date', 'home_score', 'away_score'])['odds']
      .mean()
      .reset_index()
    )
    
    print('** done')
    return df

def get_stats_odds(driver, tables_names, match_date, stat):
    '''Takes a selenium webdriver
    and returns dataframe of probabilities of the scoreline.
    Expects stat = 'Anytime Assist' or 'Anytime Goal Scorer'
    '''
    
    driver.execute_script("window.scrollTo(0, 150)")
    try:
        idx = tables_names[stat]
    except:
        print(f"**Couldn't find a table for {stat}.")
        return
    
    # Click on the dropdown to expand the correct score block, and load the score data elements
    driver.execute_script("arguments[0].scrollIntoView();", driver.find_elements('class name', 'mtb-header')[idx])
    driver.find_elements('class name', 'mtb-header')[idx].click()
    stat_data = driver.find_elements('class name', 'mtb-content')[idx]
    
    # Scroll to the "view more" button and click it, so all data is available
    driver.execute_script("arguments[0].scrollIntoView();", stat_data.find_element('class name', 'ot-view-more'))
    stat_data.find_element('class name', 'ot-view-more').click()
    
    # Loop through each row of scoreline data to build table.
    print(f'** collecting {stat} data')
    player = []
    odds = []
    for row in stat_data.find_elements('class name', 'results-row'):
        odds_grid = row.find_element('class name', 'grid-odds-list').find_elements('tag name', 'li')
        for odds_val in odds_grid:
            if odds_val.get_attribute('data-runner'):
                player.append(odds_val.get_attribute('data-runner'))
                odds.append(odds_val.get_attribute('data-decimal'))
                
    # Make Dataframe with Resulting Data
    stat_col = 'odds_' + stat.replace('Anytime ', '').lower().replace(' ', '_')
    df = pd.DataFrame(zip(player, odds), columns=['player', stat_col])
    
    #odds of 0 don't make sense, remove
    df[stat_col] = df[stat_col].astype('float')
    df = df[df[stat_col] > 0]
    
    aggs = ['mean', 'min', 'max', 'count']
    
    df = (df
      .groupby(['player'])[stat_col]
      .agg(aggs)
      .reset_index()
      .rename(columns={a: f'{stat_col}_{a}' for a in aggs})
    )
    
    df['match_date'] = match_date
    
    print('** done')
    return df

def construct_scorelines_dataframe(scraped_scorelines):
    """ Takes the results of the all_scorelines dataframe, and organizes into a more
    usable dataframe.
    """
    
    scorelines_h = (scraped_scorelines[['home_team', 'home_score', 'away_score', 'match_date', 'odds']]
                       .rename(columns={'home_team': 'team', 'away_team': 'opp_team',
                                        'home_score': 'gf', 'away_score': 'ga'})
                       )

    scorelines_a = (scraped_scorelines[['away_team', 'away_score', 'home_score', 'match_date', 'odds']]
                       .rename(columns={'away_team': 'team', 'home_team': 'opp_team',
                                        'away_score': 'gf', 'home_score': 'ga'})
                       )
    
    scorelines_h['at_home'] = 1
    scorelines_a['at_home'] = 0

    all_scorelines = pd.concat([scorelines_h, scorelines_a])

    # convert goals for and against to int
    all_scorelines['gf'] = all_scorelines.gf.astype('int')
    all_scorelines['ga'] = all_scorelines.ga.astype('int')

    # Drop scorelines with over 5 goals
    all_scorelines = all_scorelines[(all_scorelines.gf <= 5) & (all_scorelines.ga <= 5)]

    # convert odds to implied probability
    all_scorelines['proba'] = 1 / all_scorelines.odds

    # Convert match_date column to datetime.
    all_scorelines['match_date'] = pd.to_datetime(all_scorelines.match_date + [' 2022'], format='%a %d %b %Y')

    # The bookies pad their odds, so the proabilities are over 100%. Readjust.
    all_scorelines.proba = all_scorelines.proba / all_scorelines.groupby('team')['proba'].transform(sum)
    
    return all_scorelines


def construct_assists_goals_dataframe(all_assists, all_goals):
    """Takes the results of the all_assists and all_goals dataframe, and organizes into 
    a more usable dataframe.
    """
    
    df = pd.merge(all_assists, all_goals, how='outer', on=['player', 'match_date'])
    
    # Convert match date to datetime
    df['match_date'] = pd.to_datetime(df.match_date + [' 2022'], format='%a %d %b %Y')
    
    # Average all bookeeper odds per play to calculate probabilities
    df['proba_assist'] = 1 / df.odds_assist_mean
    df['proba_goal'] = 1 / df.odds_goalscorer_mean
    
    # If player has assist odds from less than 2 bookies, or goalscorer odds from less than 6 bookies,
    # remove player from output dataframes. These probabilities have been shown not to be trustworthy. 
    df = df[(df.odds_assist_count > 1) & (df.odds_goalscorer_count > 5)]
    
    return df

def collect_previously_scraped_slugs(match_slugs):
    """Checks to see if some matches have already been scraped today, and returns a 
    list of what slugs have been scraped, and what slugs are remaining.
    """
    
     # Check to see if data has already been scraped for today
    date_path = date.today().strftime('%Y_%m_%d')
    path = f'../data/historical/{date_path}/raw_scraped_records'
    if os.path.exists(path):
        with open(f'{path}/match_slugs.json', 'r') as f:
            previously_scraped_match_slugs = json.load(f)
        
        # If data has already been scraped for today, remove those match slugs    
        remaining_match_slugs= (
            [slug for slug in match_slugs if slug not in previously_scraped_match_slugs]
        )
        
        count_remaining_matches = len(remaining_match_slugs)
        if count_remaining_matches < len(match_slugs):
            print(
                f"""{len(match_slugs) - count_remaining_matches} matches have already been scraped.{count_remaining_matches} matches remaining."""
            )
        
    else:
        remaining_match_slugs = match_slugs
        previously_scraped_match_slugs = []  
    
    return remaining_match_slugs, previously_scraped_match_slugs

def collect_previously_scraped_data(match_slugs):
    """Checks to see if some data has already been scraped today.
    If so, returns the raw scraped dataframes.
    If not, returns empty dataframes
    """
    
     # Check to see if data has already been scraped for today
    date_path = date.today().strftime('%Y_%m_%d')
    path = f'../data/historical/{date_path}/raw_scraped_records'
    if os.path.exists(path):
        # Gather raw scraped data
        all_scorelines = pd.read_pickle(f'{path}/raw_scraped_scorelines.pkl')
        all_assists = pd.read_pickle(f'{path}/raw_scraped_assists.pkl')
        all_goals = pd.read_pickle(f'{path}/raw_scraped_goals.pkl')
        
    else:
        all_scorelines = pd.DataFrame()
        all_assists = pd.DataFrame()
        all_goals = pd.DataFrame()    
    
    return all_scorelines, all_assists, all_goals

def record_match_to_previously_scraped_list(previously_scraped_list, match):
    previously_scraped_list.append(match)

    # save all to raw_scraped_records folder
    date_path = date.today().strftime('%Y_%m_%d')
    path = f'../data/historical/{date_path}/raw_scraped_records'

    with open(f'{path}/match_slugs.json', 'w') as f:
        # indent=2 is not needed but makes the file human-readable 
        # if the data is nested
        json.dump(previously_scraped_list, f, indent=2)
    
    return
    

def run_match_scraper(match, previously_scraped_match_slugs, all_scorelines, all_assists, all_goals, driver):
    """Takes one match slug, and attempts to scrape data. If scrape is successful, 
    appends to previously scraped data from the same day.
    """
    driver, tables_names, team_names, match_date = get_match_info(driver, match)
        
    # Try Scraping Results, If error, print to screen, and continue
    try:
        game_df_scoreline = get_scoreline_odds(driver, tables_names, match_date, team_names)
        game_df_assists = get_stats_odds(driver, tables_names, match_date, 'Anytime Assist')
        game_df_goals = get_stats_odds(driver, tables_names, match_date,'Anytime Goalscorer')
        
        # Record Results to dataframes
        all_scorelines = pd.concat([all_scorelines, game_df_scoreline])
        all_assists = pd.concat([all_assists, game_df_assists])
        all_goals = pd.concat([all_goals, game_df_goals])
        
        # if path doesn't already exist, create it
        date_path = date.today().strftime('%Y_%m_%d')
        path = f'../data/historical/{date_path}/raw_scraped_records'
        if not os.path.exists(path):
            os.makedirs(path)
        
        # Save scraped data    
        all_scorelines.to_pickle(f'{path}/raw_scraped_scorelines.pkl')
        all_assists.to_pickle(f'{path}/raw_scraped_assists.pkl')
        all_goals.to_pickle(f'{path}/raw_scraped_goals.pkl')
        
        # Record that match has been scraped sucessfully in date folder
        record_match_to_previously_scraped_list(previously_scraped_match_slugs, match)
    
    except Exception as e:
        print(f'While scraping {match}, encountered error: {e}')
        
    return

def orchestrator():
    """This function gathers all possible match slugs to scrape, and checks that list
    against the previous scraped slugs, if any. If any slugs are remaining to be scraped,
    try scraping them, up to 10 total attempts.
    """
    
    all_match_slugs = get_match_slugs()    
    attempts_count = 1
    driver = webdriver.Chrome('/usr/local/bin/chromedriver')
    
    while attempts_count <= 10:
        remaining_match_slugs, previously_scraped_match_slugs = collect_previously_scraped_slugs(all_match_slugs)
        
        if len(remaining_match_slugs) > 0:
            print(f'Scraping attempt {attempts_count}')
            for idx, match in enumerate(remaining_match_slugs):
                print(f'Match {idx} of {len(remaining_match_slugs)}:')
                
                # Collect previous data to append to, and run scraper
                all_scorelines, all_assists, all_goals = collect_previously_scraped_data(all_match_slugs)
                run_match_scraper(match, previously_scraped_match_slugs, all_scorelines, all_assists, all_goals, driver)
                
            attempts_count += 1
        
        elif len(remaining_match_slugs) == 0:
            print('**Success: All Matches Have Been Scraped**')
            return
        
    
def final_odds_df_builder(date_path = date.today().strftime('%Y_%m_%d')):
    """Gather all scraped data, and organize into polished dataframes by running the
    construct_scorelines_dataframe and construct_assists_goals_dataframe functions.
    
    Input: date in format of '2022_10_15'. If no date provided, defaults to today.
    """
    
    path = f'../data/historical/{date_path}/raw_scraped_records'
    
    # Gather all raw scraped data
    all_scorelines = pd.read_pickle(f'{path}/raw_scraped_scorelines.pkl')
    all_assists = pd.read_pickle(f'{path}/raw_scraped_assists.pkl')
    all_goals = pd.read_pickle(f'{path}/raw_scraped_goals.pkl')
    
    scorelines_output = construct_scorelines_dataframe(all_scorelines)
    goals_assists_output = construct_assists_goals_dataframe(all_assists, all_goals)

    # save outputs as current
    scorelines_output.to_pickle(f'../data/scoreline_probabilities.pkl')
    goals_assists_output.to_pickle(f'../data/goals_assists_odds.pkl')
    
    # save outputs to historical folder
    scorelines_output.to_pickle(f'{path}/scoreline_probabilities.pkl')
    goals_assists_output.to_pickle(f'{path}/goals_assists_odds.pkl')