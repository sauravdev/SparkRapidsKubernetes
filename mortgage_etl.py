#!/usr/bin/env python
# coding: utf-8


import time
from pyspark import broadcast
from pyspark.sql import SparkSession
from pyspark.sql.functions import *
from pyspark.sql.types import *

def _get_quarter_from_csv_file_name():
    return substring_index(substring_index(input_file_name(), '.', 1), '_', -1)

_csv_perf_schema = StructType([
    StructField('loan_id', LongType()),
    StructField('monthly_reporting_period', StringType()),
    StructField('servicer', StringType()),
    StructField('interest_rate', DoubleType()),
    StructField('current_actual_upb', DoubleType()),
    StructField('loan_age', DoubleType()),
    StructField('remaining_months_to_legal_maturity', DoubleType()),
    StructField('adj_remaining_months_to_maturity', DoubleType()),
    StructField('maturity_date', StringType()),
    StructField('msa', DoubleType()),
    StructField('current_loan_delinquency_status', IntegerType()),
    StructField('mod_flag', StringType()),
    StructField('zero_balance_code', StringType()),
    StructField('zero_balance_effective_date', StringType()),
    StructField('last_paid_installment_date', StringType()),
    StructField('foreclosed_after', StringType()),
    StructField('disposition_date', StringType()),
    StructField('foreclosure_costs', DoubleType()),
    StructField('prop_preservation_and_repair_costs', DoubleType()),
    StructField('asset_recovery_costs', DoubleType()),
    StructField('misc_holding_expenses', DoubleType()),
    StructField('holding_taxes', DoubleType()),
    StructField('net_sale_proceeds', DoubleType()),
    StructField('credit_enhancement_proceeds', DoubleType()),
    StructField('repurchase_make_whole_proceeds', StringType()),
    StructField('other_foreclosure_proceeds', DoubleType()),
    StructField('non_interest_bearing_upb', DoubleType()),
    StructField('principal_forgiveness_upb', StringType()),
    StructField('repurchase_make_whole_proceeds_flag', StringType()),
    StructField('foreclosure_principal_write_off_amount', StringType()),
    StructField('servicing_activity_indicator', StringType())])
_csv_acq_schema = StructType([
    StructField('loan_id', LongType()),
    StructField('orig_channel', StringType()),
    StructField('seller_name', StringType()),
    StructField('orig_interest_rate', DoubleType()),
    StructField('orig_upb', IntegerType()),
    StructField('orig_loan_term', IntegerType()),
    StructField('orig_date', StringType()),
    StructField('first_pay_date', StringType()),
    StructField('orig_ltv', DoubleType()),
    StructField('orig_cltv', DoubleType()),
    StructField('num_borrowers', DoubleType()),
    StructField('dti', DoubleType()),
    StructField('borrower_credit_score', DoubleType()),
    StructField('first_home_buyer', StringType()),
    StructField('loan_purpose', StringType()),
    StructField('property_type', StringType()),
    StructField('num_units', IntegerType()),
    StructField('occupancy_status', StringType()),
    StructField('property_state', StringType()),
    StructField('zip', IntegerType()),
    StructField('mortgage_insurance_percent', DoubleType()),
    StructField('product_type', StringType()),
    StructField('coborrow_credit_score', DoubleType()),
    StructField('mortgage_insurance_type', DoubleType()),
    StructField('relocation_mortgage_indicator', StringType())])

def read_perf_csv(spark, path):
    return spark.read.format('csv')             .option('nullValue', '')             .option('header', 'false')             .option('delimiter', '|')             .schema(_csv_perf_schema)             .load(path)             .withColumn('quarter', _get_quarter_from_csv_file_name())

def read_acq_csv(spark, path):
    return spark.read.format('csv')             .option('nullValue', '')             .option('header', 'false')             .option('delimiter', '|')             .schema(_csv_acq_schema)             .load(path)             .withColumn('quarter', _get_quarter_from_csv_file_name())

def _parse_dates(perf):
    return perf             .withColumn('monthly_reporting_period', to_date(col('monthly_reporting_period'), 'MM/dd/yyyy'))             .withColumn('monthly_reporting_period_month', month(col('monthly_reporting_period')))             .withColumn('monthly_reporting_period_year', year(col('monthly_reporting_period')))             .withColumn('monthly_reporting_period_day', dayofmonth(col('monthly_reporting_period')))             .withColumn('last_paid_installment_date', to_date(col('last_paid_installment_date'), 'MM/dd/yyyy'))             .withColumn('foreclosed_after', to_date(col('foreclosed_after'), 'MM/dd/yyyy'))             .withColumn('disposition_date', to_date(col('disposition_date'), 'MM/dd/yyyy'))             .withColumn('maturity_date', to_date(col('maturity_date'), 'MM/yyyy'))             .withColumn('zero_balance_effective_date', to_date(col('zero_balance_effective_date'), 'MM/yyyy'))

def _create_perf_deliquency(spark, perf):
    aggDF = perf.select(
            col("quarter"),
            col("loan_id"),
            col("current_loan_delinquency_status"),
            when(col("current_loan_delinquency_status") >= 1, col("monthly_reporting_period")).alias("delinquency_30"),
            when(col("current_loan_delinquency_status") >= 3, col("monthly_reporting_period")).alias("delinquency_90"),
            when(col("current_loan_delinquency_status") >= 6, col("monthly_reporting_period")).alias("delinquency_180")) \
                    .groupBy("quarter", "loan_id") \
                    .agg(
                            max("current_loan_delinquency_status").alias("delinquency_12"),
                            min("delinquency_30").alias("delinquency_30"),
                            min("delinquency_90").alias("delinquency_90"),
                            min("delinquency_180").alias("delinquency_180")) \
                                    .select(
                                            col("quarter"),
                                            col("loan_id"),
                                            (col("delinquency_12") >= 1).alias("ever_30"),
                                            (col("delinquency_12") >= 3).alias("ever_90"),
                                            (col("delinquency_12") >= 6).alias("ever_180"),
                                            col("delinquency_30"),
                                            col("delinquency_90"),
                                            col("delinquency_180"))
    joinedDf = perf             .withColumnRenamed("monthly_reporting_period", "timestamp")             .withColumnRenamed("monthly_reporting_period_month", "timestamp_month")             .withColumnRenamed("monthly_reporting_period_year", "timestamp_year")             .withColumnRenamed("current_loan_delinquency_status", "delinquency_12")             .withColumnRenamed("current_actual_upb", "upb_12")             .select("quarter", "loan_id", "timestamp", "delinquency_12", "upb_12", "timestamp_month", "timestamp_year")             .join(aggDF, ["loan_id", "quarter"], "left_outer")

    # calculate the 12 month delinquency and upb values
    months = 12
    monthArray = [lit(x) for x in range(0, 12)]
    # explode on a small amount of data is actually slightly more efficient than a cross join
    testDf = joinedDf             .withColumn("month_y", explode(array(monthArray)))             .select(
                    col("quarter"),
                    floor(((col("timestamp_year") * 12 + col("timestamp_month")) - 24000) / months).alias("josh_mody"),
                    floor(((col("timestamp_year") * 12 + col("timestamp_month")) - 24000 - col("month_y")) / months).alias("josh_mody_n"),
                    col("ever_30"),
                    col("ever_90"),
                    col("ever_180"),
                    col("delinquency_30"),
                    col("delinquency_90"),
                    col("delinquency_180"),
                    col("loan_id"),
                    col("month_y"),
                    col("delinquency_12"),
                    col("upb_12")) \
                            .groupBy("quarter", "loan_id", "josh_mody_n", "ever_30", "ever_90", "ever_180", "delinquency_30", "delinquency_90", "delinquency_180", "month_y") \
                            .agg(max("delinquency_12").alias("delinquency_12"), min("upb_12").alias("upb_12")) \
                            .withColumn("timestamp_year", floor((lit(24000) + (col("josh_mody_n") * lit(months)) + (col("month_y") - 1)) / lit(12))) \
                            .selectExpr('*', 'pmod(24000 + (josh_mody_n * {}) + month_y, 12) as timestamp_month_tmp'.format(months)) \
                            .withColumn("timestamp_month", when(col("timestamp_month_tmp") == lit(0), lit(12)).otherwise(col("timestamp_month_tmp"))) \
                            .withColumn("delinquency_12", ((col("delinquency_12") > 3).cast("int") + (col("upb_12") == 0).cast("int")).alias("delinquency_12")) \
                            .drop("timestamp_month_tmp", "josh_mody_n", "month_y")

    return perf.withColumnRenamed("monthly_reporting_period_month", "timestamp_month")             .withColumnRenamed("monthly_reporting_period_year", "timestamp_year")             .join(testDf, ["quarter", "loan_id", "timestamp_year", "timestamp_month"], "left")             .drop("timestamp_year", "timestamp_month")

_name_mapping = [
        ("WITMER FUNDING, LLC", "Witmer"),
        ("WELLS FARGO CREDIT RISK TRANSFER SECURITIES TRUST 2015", "Wells Fargo"),
        ("WELLS FARGO BANK,  NA" , "Wells Fargo"),
        ("WELLS FARGO BANK, N.A." , "Wells Fargo"),
        ("WELLS FARGO BANK, NA" , "Wells Fargo"),
        ("USAA FEDERAL SAVINGS BANK" , "USAA"),
        ("UNITED SHORE FINANCIAL SERVICES, LLC D\\/B\\/A UNITED WHOLESALE MORTGAGE" , "United Seq(e"),
        ("U.S. BANK N.A." , "US Bank"),
        ("SUNTRUST MORTGAGE INC." , "Suntrust"),
        ("STONEGATE MORTGAGE CORPORATION" , "Stonegate Mortgage"),
        ("STEARNS LENDING, LLC" , "Stearns Lending"),
        ("STEARNS LENDING, INC." , "Stearns Lending"),
        ("SIERRA PACIFIC MORTGAGE COMPANY, INC." , "Sierra Pacific Mortgage"),
        ("REGIONS BANK" , "Regions"),
        ("RBC MORTGAGE COMPANY" , "RBC"),
        ("QUICKEN LOANS INC." , "Quicken Loans"),
        ("PULTE MORTGAGE, L.L.C." , "Pulte Mortgage"),
        ("PROVIDENT FUNDING ASSOCIATES, L.P." , "Provident Funding"),
        ("PROSPECT MORTGAGE, LLC" , "Prospect Mortgage"),
        ("PRINCIPAL RESIDENTIAL MORTGAGE CAPITAL RESOURCES, LLC" , "Principal Residential"),
        ("PNC BANK, N.A." , "PNC"),
        ("PMT CREDIT RISK TRANSFER TRUST 2015-2" , "PennyMac"),
        ("PHH MORTGAGE CORPORATION" , "PHH Mortgage"),
        ("PENNYMAC CORP." , "PennyMac"),
        ("PACIFIC UNION FINANCIAL, LLC" , "Other"),
        ("OTHER" , "Other"),
        ("NYCB MORTGAGE COMPANY, LLC" , "NYCB"),
        ("NEW YORK COMMUNITY BANK" , "NYCB"),
        ("NETBANK FUNDING SERVICES" , "Netbank"),
        ("NATIONSTAR MORTGAGE, LLC" , "Nationstar Mortgage"),
        ("METLIFE BANK, NA" , "Metlife"),
        ("LOANDEPOT.COM, LLC" , "LoanDepot.com"),
        ("J.P. MORGAN MADISON AVENUE SECURITIES TRUST, SERIES 2015-1" , "JP Morgan Chase"),
        ("J.P. MORGAN MADISON AVENUE SECURITIES TRUST, SERIES 2014-1" , "JP Morgan Chase"),
        ("JPMORGAN CHASE BANK, NATIONAL ASSOCIATION" , "JP Morgan Chase"),
        ("JPMORGAN CHASE BANK, NA" , "JP Morgan Chase"),
        ("JP MORGAN CHASE BANK, NA" , "JP Morgan Chase"),
        ("IRWIN MORTGAGE, CORPORATION" , "Irwin Mortgage"),
        ("IMPAC MORTGAGE CORP." , "Impac Mortgage"),
        ("HSBC BANK USA, NATIONAL ASSOCIATION" , "HSBC"),
        ("HOMEWARD RESIDENTIAL, INC." , "Homeward Mortgage"),
        ("HOMESTREET BANK" , "Other"),
        ("HOMEBRIDGE FINANCIAL SERVICES, INC." , "HomeBridge"),
        ("HARWOOD STREET FUNDING I, LLC" , "Harwood Mortgage"),
        ("GUILD MORTGAGE COMPANY" , "Guild Mortgage"),
        ("GMAC MORTGAGE, LLC (USAA FEDERAL SAVINGS BANK)" , "GMAC"),
        ("GMAC MORTGAGE, LLC" , "GMAC"),
        ("GMAC (USAA)" , "GMAC"),
        ("FREMONT BANK" , "Fremont Bank"),
        ("FREEDOM MORTGAGE CORP." , "Freedom Mortgage"),
        ("FRANKLIN AMERICAN MORTGAGE COMPANY" , "Franklin America"),
        ("FLEET NATIONAL BANK" , "Fleet National"),
        ("FLAGSTAR CAPITAL MARKETS CORPORATION" , "Flagstar Bank"),
        ("FLAGSTAR BANK, FSB" , "Flagstar Bank"),
        ("FIRST TENNESSEE BANK NATIONAL ASSOCIATION" , "Other"),
        ("FIFTH THIRD BANK" , "Fifth Third Bank"),
        ("FEDERAL HOME LOAN BANK OF CHICAGO" , "Fedral Home of Chicago"),
        ("FDIC, RECEIVER, INDYMAC FEDERAL BANK FSB" , "FDIC"),
        ("DOWNEY SAVINGS AND LOAN ASSOCIATION, F.A." , "Downey Mortgage"),
        ("DITECH FINANCIAL LLC" , "Ditech"),
        ("CITIMORTGAGE, INC." , "Citi"),
        ("CHICAGO MORTGAGE SOLUTIONS DBA INTERFIRST MORTGAGE COMPANY" , "Chicago Mortgage"),
        ("CHICAGO MORTGAGE SOLUTIONS DBA INTERBANK MORTGAGE COMPANY" , "Chicago Mortgage"),
        ("CHASE HOME FINANCE, LLC" , "JP Morgan Chase"),
        ("CHASE HOME FINANCE FRANKLIN AMERICAN MORTGAGE COMPANY" , "JP Morgan Chase"),
        ("CHASE HOME FINANCE (CIE 1)" , "JP Morgan Chase"),
        ("CHASE HOME FINANCE" , "JP Morgan Chase"),
        ("CASHCALL, INC." , "CashCall"),
        ("CAPITAL ONE, NATIONAL ASSOCIATION" , "Capital One"),
        ("CALIBER HOME LOANS, INC." , "Caliber Funding"),
        ("BISHOPS GATE RESIDENTIAL MORTGAGE TRUST" , "Bishops Gate Mortgage"),
        ("BANK OF AMERICA, N.A." , "Bank of America"),
        ("AMTRUST BANK" , "AmTrust"),
        ("AMERISAVE MORTGAGE CORPORATION" , "Amerisave"),
        ("AMERIHOME MORTGAGE COMPANY, LLC" , "AmeriHome Mortgage"),
        ("ALLY BANK" , "Ally Bank"),
        ("ACADEMY MORTGAGE CORPORATION" , "Academy Mortgage"),
        ("NO CASH-OUT REFINANCE" , "OTHER REFINANCE"),
        ("REFINANCE - NOT SPECIFIED" , "OTHER REFINANCE"),
        ("Other REFINANCE" , "OTHER REFINANCE")]

def _create_acquisition(spark, acq):
    nameMapping = spark.createDataFrame(_name_mapping, ["from_seller_name", "to_seller_name"])
    return acq.join(nameMapping, col("seller_name") == col("from_seller_name"), "left")       .drop("from_seller_name")       .withColumn("old_name", col("seller_name"))       .withColumn("seller_name", coalesce(col("to_seller_name"), col("seller_name")))       .drop("to_seller_name")       .withColumn("orig_date", to_date(col("orig_date"), "MM/yyyy"))       .withColumn("first_pay_date", to_date(col("first_pay_date"), "MM/yyyy")) 
def run_mortgage(spark, perf, acq):
    parsed_perf = _parse_dates(perf)
    perf_deliqency = _create_perf_deliquency(spark, parsed_perf)
    cleaned_acq = _create_acquisition(spark, acq)
    return perf_deliqency.join(cleaned_acq, ["loan_id", "quarter"], "inner").drop("quarter")


# In[3]:

from pyspark import SparkContext, SparkConf


if __name__ == '__main__':
    conf = SparkConf().setAppName("app")
    sc = SparkContext(conf=conf)
    orig_perf_path='/opt/spark/usecase/tables/mortgage/perf/*'
    orig_acq_path='/opt/spark/usecase/tables/mortgage/acq/*'
    tmp_perf_path='/opt/spark/usecase/tables/mortgage_parquet_gpu/perf/'
    tmp_acq_path='/opt/spark/usecase/tables/mortgage_parquet_gpu/acq/'
    output_path='/opt/spark/usecase/tables/mortgage_parquet_gpu/output/'
    spark.conf.set('spark.rapids.sql.enabled','true')
    spark.conf.set('spark.rapids.sql.explain', 'ALL')
    spark.conf.set('spark.rapids.sql.incompatibleOps.enabled', 'true')
    spark.conf.set('spark.rapids.sql.batchSizeBytes', '512M')
    spark.conf.set('spark.rapids.sql.reader.batchSizeBytes', '768M')
    # Lets transcode the data first
    start = time.time()
    # we want a few big files instead of lots of small files
    spark.conf.set('spark.sql.files.maxPartitionBytes', '200G')
    acq = read_acq_csv(spark, orig_acq_path)
    acq.repartition(12).write.parquet(tmp_acq_path, mode='overwrite')
    perf = read_perf_csv(spark, orig_perf_path)
    perf.coalesce(96).write.parquet(tmp_perf_path, mode='overwrite')
    end = time.time()
    print(end - start)
    # Now lets actually process the data\n",
    start = time.time()
    spark.conf.set('spark.sql.files.maxPartitionBytes', '1G')
    spark.conf.set('spark.sql.shuffle.partitions', '192')
    perf = spark.read.parquet(tmp_perf_path)
    acq = spark.read.parquet(tmp_acq_path)
    out = run_mortgage(spark, perf, acq)
    out.write.parquet(output_path, mode='overwrite')
    end = time.time()
    print(end - start)


