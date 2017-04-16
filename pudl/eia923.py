"""
Retrieve data from EIA Form 923 spreadsheets for analysis.

This modules pulls data from EIA's published Excel spreadsheets.

This code is for use analyzing EIA Form 923 data, years 2008-2016 Current
version is for years 2011-2016, which have standardized naming conventions and
file formatting.
"""

import pandas as pd
import os.path
from pudl import settings, constants

###########################################################################
# Helper functions & other objects to ingest & process Energy Information
# Administration (EIA) Form 923 data.
###########################################################################


def datadir(year):
    """
    Data directory search for EIA Form 923.

    Args:
        year (int): The year that we're trying to read data for.
    Returns:
        path to appropriate EIA 923 data directory.
    """
    # These are the only years we've got...
    assert year in range(2001, 2017)
    if(year < 2008):
        return(os.path.join(settings.EIA923_DATA_DIR,
                            'f906920_{}'.format(year)))
    else:
        return(os.path.join(settings.EIA923_DATA_DIR, 'f923_{}'.format(year)))


def get_eia923_file(yr):
    """
    Given a year, return the appopriate EIA923 excel file.

    Args:
        year (int): The year that we're trying to read data for.
    Returns:
        path to EIA 923 spreadsheets corresponding to a given year.
    """
    from glob import glob

    assert(yr > 2008), "EIA923 file selection only works for 2008 & later."
    return(glob(os.path.join(datadir(yr), '*2_3_4*'))[0])


def get_eia923_column_map(page, year):
    """
    Given a year and EIA923 page, return info required to slurp it from Excel.

    The format of the EIA923 has changed slightly over the years, and so it
    is not completely straightforward to pull information from the spreadsheets
    into our analytical framework. This function looks up a map of the various
    tabs in the spreadsheet by year and page, and returns the information
    needed to name the data fields in a standardized way, and pull the right
    cells from each year & page into our database.

    Args:
        page (str): The string label indicating which page of the EIA923 we
            are attempting to read in. Must be one of the following:
                - 'generation_fuel'
                - 'stocks'
                - 'boiler_fuel'
                - 'generator'
                - 'fuel_receipts_costs'
                - 'plant_frame'
        year (int): The year that we're trying to read data for.

    Returns:
        sheetname (int): An integer indicating which page in the worksheet
            the data should be pulled from. 0 is the first page, 1 is the
            second page, etc. For use by pandas.read_excel()
        skiprows (int): An integer indicating how many rows should be skipped
            at the top of the sheet being read in, before the header row that
            contains the strings which will be converted into column names in
            the dataframe which is created by pandas.read_excel()
        column_map (dict): A dictionary that maps the names of the columns
            in the year being read in, to the canonical EIA923 column names
            (i.e. the column names as they are in 2014-2016). This dictionary
            will be used by DataFrame.rename(). The keys are the column names
            in the dataframe as read from older years, and the values are the
            canonmical column names.  All should be stripped of leading and
            trailing whitespace, converted to lower case, and have internal
            non-alphanumeric characters replaced with underscores.
    """
    sheetname = constants.tab_map_eia923.get_value(year, page)
    skiprows = constants.skiprows_eia923.get_value(year, page)

    page_to_df = {
        'generation_fuel': constants.generation_fuel_map_eia923,
        'stocks': constants.stocks_map_eia923,
        'boiler_fuel': constants.boiler_fuel_map_eia923,
        'generator': constants.generator_map_eia923,
        'fuel_receipts_costs': constants.fuel_receipts_costs_map_eia923,
        'plant_frame': constants.plant_frame_map_eia923}

    d = page_to_df[page].loc[year].to_dict()

    column_map = {}
    for k, v in d.items():
        column_map[v] = k

    return((sheetname, skiprows, column_map))


def get_eia923_page(page, eia923_xlsx,
                    years=[2011, 2012, 2013, 2014, 2015, 2016],
                    verbose=True):
    """
    Read a single table from several years of EIA923 data. Return a DataFrame.

    Args:
        page (str): The string label indicating which page of the EIA923 we
        are attempting to read in. The page argument must be exactly one of the
        following strings:
            - 'generation_fuel'
            - 'stocks'
            - 'boiler_fuel'
            - 'generator'
            - 'fuel_receipts_costs'
            - 'plant_frame'

      years (list): The set of years to read into the dataframe.

    Returns:
        pandas.DataFrame: A dataframe containing the data from the selected
            page and selected years from EIA 923.
    """
    assert min(years) >= 2009,\
        "EIA923 works for 2009 and later. {} requested.".format(min(years))
    assert page in constants.tab_map_eia923.columns and page != 'year_index',\
        "Unrecognized EIA 923 page: {}".format(page)

    if verbose:
        print('Converting EIA 923 {} to DataFrame...'.format(page))
    df = pd.DataFrame()
    for yr in years:
        sheetname, skiprows, column_map = get_eia923_column_map(page, yr)
        newdata = pd.read_excel(eia923_xlsx[yr],
                                sheetname=sheetname,
                                skiprows=skiprows)

        # Clean column names: lowercase, underscores instead of white space,
        # no non-alphanumeric characters
        newdata.columns = newdata.columns.str.replace('[^0-9a-zA-Z]+', ' ')
        newdata.columns = newdata.columns.str.strip().str.lower()
        newdata.columns = newdata.columns.str.replace(' ', '_')

        # Drop columns that start with "reserved" because they are empty
        to_drop = [c for c in newdata.columns if c[:8] == 'reserved']
        newdata.drop(to_drop, axis=1, inplace=True)

        # stocks tab is missing a YEAR column for some reason. Add it!
        if(page == 'stocks'):
            newdata['year'] = yr

        newdata = newdata.rename(columns=column_map)
        if(page == 'stocks'):
            newdata = newdata.rename(columns={
                'unnamed_0': 'census_division_and_state'})

        # Drop the fields with plant_id 99999.
        # These are state index
        if(page != 'stocks'):
            newdata = newdata.loc[newdata['plant_id'] != 99999]

        df = df.append(newdata)

    # We could also do additional cleanup here -- for example:
    #  - Substituting ISO-3166 3 letter country codes for the ad-hoc EIA
    #    2-letter country codes.
    #  - Replacing Y/N string values with True/False Booleans
    #  - Replacing '.' strings with np.nan values as appropriate.

    return(df)


def get_eia923_xlsx(years):
    """
    Read in Excel files to create Excel objects.

    Rather than reading in the same Excel files several times, we can just
    read them each in once (one per year) and use the ExcelFile object to
    refer back to the data in memory.

    Args:
        years: The years that we're trying to read data for.
    Returns:
        xlsx file of EIA Form 923 for input year(s)
    """
    eia923_xlsx = {}
    for yr in years:
        print("Reading EIA 923 spreadsheet data for {}.".format(yr))
        eia923_xlsx[yr] = pd.ExcelFile(get_eia923_file(yr))
    return(eia923_xlsx)


def get_eia923_plant_info(years, eia923_xlsx):
    """
    Generate an exhaustive list of EIA 923 plants.

    Most plants are listed in the 'Plant Frame' tabs for each year. The 'Plant
    Frame' tab does not exist before 2011 and there is plant specific
    information that is not included in the 'Plant Frame' tab that will be
    pulled into the plant info table. For years before 2011, it will be used to
    generate the exhaustive list of plants.

    This function will be used in two ways: to populate the plant info table
    and to check the plant mapping to find missing plants.

    Args:
        years: The year that we're trying to read data for.
        eia923_xlsx: required and should not be modified
    Returns:
        Data frame that populates the plant info table
        A check of plant mapping to identify missing plants
    """
    recent_years = [y for y in years if y >= 2011]

    df_all_years = pd.DataFrame(columns=['plant_id'])

    pf = pd.DataFrame(columns=['plant_id', 'plant_state',
                               'combined_heat_power',
                               'eia_sector', 'naics_code',
                               'reporting_frequency', 'year'])
    if (len(recent_years) > 0):
        pf = get_eia923_page('plant_frame', eia923_xlsx, years=recent_years)
        pf = pf[['plant_id', 'plant_state',
                 'combined_heat_power',
                 'eia_sector', 'naics_code',
                 'reporting_frequency', 'year']]
        pf = pf.sort_values(['year', ], ascending=False)

    gf = get_eia923_page('generation_fuel', eia923_xlsx, years=years)
    gf = gf[['plant_id', 'plant_state',
             'combined_heat_power', 'census_region', 'nerc_region', 'year']]
    gf = gf.sort_values(['year', ], ascending=False)
    gf = gf.drop_duplicates(subset='plant_id')

    bf = get_eia923_page('boiler_fuel', eia923_xlsx, years=years)
    bf = bf[['plant_id', 'plant_state',
             'combined_heat_power',
             'naics_code', 'naics_code',
             'eia_sector', 'census_region', 'nerc_region', 'year']]
    bf = bf.sort_values(['year'], ascending=False)
    bf = bf.drop_duplicates(subset='plant_id')

    g = get_eia923_page('generator', eia923_xlsx, years=years)
    g = g[['plant_id', 'plant_state', 'combined_heat_power',
           'census_region', 'nerc_region', 'naics_code', 'eia_sector', 'year']]
    g = g.sort_values(['year'], ascending=False)
    g = g.drop_duplicates(subset='plant_id')

    frc = get_eia923_page('fuel_receipts_costs', eia923_xlsx, years=years)
    frc = frc[['plant_id', 'plant_state', 'year']]
    frc = frc.sort_values(['plant_id'], ascending=False)
    frc = frc.drop_duplicates(subset='plant_id')

    plant_ids = pd.concat(
        [pf.plant_id, gf.plant_id, bf.plant_id, g.plant_id, frc.plant_id],)
    plant_ids = plant_ids.unique()

    df_all_years = pd.DataFrame(columns=['plant_id'])
    df_all_years['plant_id'] = plant_ids

    df_all_years = df_all_years.merge(pf, on='plant_id', how='left')
    df_all_years = df_all_years.merge(gf[['plant_id', 'census_region',
                                          'nerc_region']],
                                      on='plant_id', how='left')
    df_all_years = df_all_years.sort_values(['nerc_region',
                                             'plant_state',
                                             'eia_sector'], na_position='last')

    df_all_years = df_all_years.drop_duplicates('plant_id')
    df_all_years = df_all_years.drop(['year', ], axis=1)

    return(df_all_years)


def yearly_to_monthly_eia923(df, md):
    """
    Convert an EIA 923 record with 12 months of data into 12 monthly records.

    Much of the data reported in EIA 923 is monthly, but all 12 months worth of
    data is reported in a single record, with one field for each of the 12
    months.  This function converts these annualized composite records into a
    set of 12 monthly records containing the same information, by parsing the
    field names for months, and adding a month field.  Non - time series data
    is retained in the same format.

    Args:
        df(pandas.DataFrame): A pandas DataFrame containing the annual
            data to be converted into monthly records.
        md(dict): a dictionary with the numbers 1 - 12 as keys, and the
            patterns used to match field names for each of the months as
            values. These patterns are also used to re - name the columns in
            the dataframe which is returned, so they need to match the entire
            portion of the column name that is month - specific.

    Returns:
        pandas.DataFrame: A dataframe containing the same data as was passed in
            via df, but with monthly records instead of annual records.
    """
    # Pull out each month's worth of data, merge it with the common columns,
    # rename columns to match the PUDL DB, add an appropriate month column,
    # and insert it into the PUDL DB.
    yearly = df.copy()
    monthly = pd.DataFrame()

    for m in md.keys():
        # Grab just the columns for the month we're working on.
        this_month = yearly.filter(regex=md[m])
        # Drop this month's data from the yearly data frame.
        yearly.drop(this_month.columns, axis=1, inplace=True)
        # Rename this month's columns to get rid of the month reference.
        this_month.columns = this_month.columns.str.replace(md[m], '')
        # Add a numerical month column corresponding to this month.
        this_month['month'] = m
        # Add this month's data to the monthly DataFrame we're building.
        monthly = pd.concat([monthly, this_month])

    # Merge the monthly data we've built up with the remaining fields in the
    # data frame we started with -- all of which should be independent of the
    # month, and apply across all 12 of the monthly records created from each
    # of the # initial annual records.
    return(yearly.merge(monthly, left_index=True, right_index=True))


def cleanstringsEIA923(field, stringmap, unmapped=None):
    """
    Clean up a field of string data in one of the Form 1 data frames.

    This function maps many different strings meant to represent the same value
    or category to a single value. In addition, white space is stripped and
    values are translated to lower case.  Optionally replace all unmapped
    values in the original field with a value (like NaN) to indicate data which
    is uncategorized or confusing.

    Args:
        field (pandas.DataFrame column): A pandas DataFrame column
            (e.g. f1_fuel["FUEL"]) whose strings will be matched, where
            possible, to categorical values from the stringmap dictionary.

        stringmap (dict): A dictionary whose keys are the strings we're mapping
            to, and whose values are the strings that get mapped.

        unmapped (str, None, NaN) is the value which strings not found in the
            stringmap dictionary should be replaced by.

    Returns:

        pandas.Series: The function returns a new pandas series/column that can
            be used to set the values of the original data.
    """
    from numpy import setdiff1d

    # Simplify the strings we're working with, to reduce the number of strings
    # we need to enumerate in the maps

    # Transform the strings to lower case, strip leading/trailing whitespace
    field = field.str.upper().str.strip()
    # remove duplicate internal whitespace
    field = field.replace('[\s+]', ' ', regex=True)

    for k in stringmap.keys():
        field = field.replace(stringmap[k], k)

    if unmapped is not None:
        badstrings = setdiff1d(field.unique(), list(stringmap.keys()))
        field = field.replace(badstrings, unmapped)

    return field
