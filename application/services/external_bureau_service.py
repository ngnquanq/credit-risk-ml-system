#!/usr/bin/env python3
"""
External Bureau Data Service

Consumes from: hc.applications.public.loan_applications (CDC topic)
Produces to: hc.application_ext

For each loan application:
1. Extract sk_id_curr from CDC message
2. Query external bureau database using bureau_client
3. Transform and enrich bureau data
4. Publish enriched features to hc.application_ext topic

Todo: The return 0 for non exist customer are kinda fix code, need to be more generic
"""

import asyncio
import time
import json
import os
from typing import Any, Dict, Optional

from confluent_kafka import Consumer, Producer
from loguru import logger

from application.services.bureau_client import fetch_bureau_by_loan_id, fetch_external_scores


class ExternalBureauService:
    def __init__(self):
        self.bootstrap_servers = os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        self.source_topic = os.getenv("CDC_SOURCE_TOPIC", "hc.applications.public.loan_applications")
        self.sink_topic = os.getenv("SINK_TOPIC_EXT", "hc.application_ext")
        self.group_id = os.getenv("CONSUMER_GROUP_ID", "external-bureau-service")
        
        # Configure consumer
        self.consumer = Consumer({
            'bootstrap.servers': self.bootstrap_servers,
            'group.id': self.group_id,
            'auto.offset.reset': 'latest',
            'enable.auto.commit': True,
        })
        
        # Configure producer
        self.producer = Producer({
            'bootstrap.servers': self.bootstrap_servers,
        })
        
        logger.info(f"External Bureau Service initialized")
        logger.info(f"Source topic: {self.source_topic}")
        logger.info(f"Sink topic: {self.sink_topic}")

    async def process_loan_application(self, sk_id_curr: str) -> Optional[Dict[str, Any]]:
        """Query external bureau data and transform for ML features."""
        try:
            sk_id_curr_int = int(sk_id_curr)
            
            # Fetch bureau data and external scores
            bureau_data = await fetch_bureau_by_loan_id(sk_id_curr_int)
            external_scores = await fetch_external_scores(sk_id_curr_int)
            # Normalize ext_source_* to float if present (guard against string types)
            for k in ("ext_source_1", "ext_source_2", "ext_source_3"):
                if k in external_scores and external_scores[k] is not None:
                    try:
                        external_scores[k] = float(external_scores[k])
                    except Exception:
                        pass
            
            # Transform bureau data into aggregated features
            bureau_features = self._transform_bureau_data(bureau_data)
            
            # Ensure required ext_source fields are present (Feast schema requirement)
            default_external_scores = {
                "ext_source_1": None,
                "ext_source_2": None, 
                "ext_source_3": None,
            }
            
            # Combine all external features with defaults first, then actual data
            external_features = {
                "sk_id_curr": sk_id_curr,
                **default_external_scores,  # Defaults first
                **external_scores,          # Actual data overwrites defaults
                **bureau_features,
                # Use epoch seconds for Feast timestamp alignment
                "ts": time.time(),
            }
            
            logger.bind(event="bureau_processed").info({
                "sk_id_curr": sk_id_curr,
                "bureau_count": len(bureau_data.get("bureau", [])),
                "balance_count": len(bureau_data.get("bureau_balance", [])),
                "has_ext_scores": bool(external_scores)
            })
            
            return external_features
            
        except Exception as e:
            logger.bind(event="bureau_error").error({
                "sk_id_curr": sk_id_curr,
                "error": str(e)
            })
            return None

    def _transform_bureau_data(self, bureau_data: Dict[str, Any]) -> Dict[str, Any]:
        """Transform raw bureau + bureau_balance into comprehensive ML features on the fly.

        Implements aggregation of two inputs:
        - bureau (account-level) -> risk + advanced utilization features
        - bureau_balance (monthly status per SK_ID_BUREAU) -> behavioral features
        Then rolls up to SK_ID_CURR-level metrics.
        """
        bureau = bureau_data.get("bureau", []) or []
        balance = bureau_data.get("bureau_balance", []) or []

        # Helpers
        def to_float(v):
            try:
                return float(v)
            except (TypeError, ValueError):
                return None

        def to_int(v):
            try:
                return int(v)
            except (TypeError, ValueError):
                return None

        def safe_div(num: float | int | None, den: float | int | None) -> float | None:
            if num is None or den in (None, 0):
                return None
            try:
                return float(num) / float(den)
            except ZeroDivisionError:
                return None

        total = len(bureau)
        if total == 0:
            # Return zeros/None when no bureau data present
            return {
                'BUREAU_TOTAL_COUNT': 0,
                'BUREAU_CREDIT_TYPES_COUNT': 0,
                'BUREAU_ACTIVE_COUNT': 0,
                'BUREAU_CLOSED_COUNT': 0,
                'BUREAU_BAD_DEBT_COUNT': 0,
                'BUREAU_SOLD_COUNT': 0,
                'BUREAU_BAD_DEBT_RATIO': None,
                'BUREAU_SOLD_RATIO': None,
                'BUREAU_HIGH_RISK_RATIO': None,
                'BUREAU_OVERDUE_DAYS_TOTAL': 0,
                'BUREAU_OVERDUE_DAYS_MEAN': None,
                'BUREAU_OVERDUE_DAYS_MAX': None,
                'BUREAU_OVERDUE_COUNT': 0,
                'BUREAU_OVERDUE_RATIO': None,
                'BUREAU_AMT_OVERDUE_TOTAL': 0.0,
                'BUREAU_AMT_OVERDUE_MEAN': None,
                'BUREAU_AMT_OVERDUE_MAX': None,
                'BUREAU_AMT_MAX_OVERDUE_EVER': None,
                'BUREAU_AMT_OVERDUE_COUNT': 0,
                'BUREAU_AMT_OVERDUE_RATIO': None,
                'BUREAU_PROLONG_TOTAL': 0,
                'BUREAU_PROLONG_MEAN': None,
                'BUREAU_PROLONG_MAX': None,
                'BUREAU_PROLONG_COUNT': 0,
                'BUREAU_PROLONG_RATIO': None,
                'BUREAU_CREDIT_UTILIZATION_RATIO': None,
                'BUREAU_DEBT_TO_CREDIT_RATIO': None,
                'BUREAU_OVERDUE_TO_CREDIT_RATIO': None,
                'BUREAU_ACTIVE_CREDIT_SUM': 0.0,
                'BUREAU_ACTIVE_DEBT_SUM': 0.0,
                'BUREAU_ACTIVE_OVERDUE_SUM': 0.0,
                'BUREAU_ACTIVE_UTILIZATION_RATIO': None,
                'BUREAU_MAXED_OUT_COUNT': 0,
                'BUREAU_MAXED_OUT_RATIO': None,
                'BUREAU_HIGH_UTIL_COUNT': 0,
                'BUREAU_HIGH_UTIL_RATIO': None,
                # Balance-derived rollups
                'BUREAU_WITH_BALANCE_COUNT': 0,
                'TOTAL_MONTHS_ALL_BUREAUS': 0,
                'TOTAL_MONTHS_ON_TIME': 0,
                'TOTAL_DPD_ALL_BUREAUS': 0,
                'TOTAL_SEVERE_DPD_MONTHS': 0,
                'WORST_DPD_RATIO': None,
                'WORST_SEVERE_DPD_RATIO': None,
                'WORST_ON_TIME_RATIO': None,
                'AVG_DPD_RATIO': None,
                'AVG_ON_TIME_RATIO': None,
                'COUNT_BUREAUS_WITH_SEVERE_DPD': 0,
                'COUNT_BUREAUS_WITH_ANY_DPD': 0,
                'OVERALL_ON_TIME_RATIO': None,
                'OVERALL_DPD_RATIO': None,
                'OVERALL_SEVERE_DPD_RATIO': None,
                'CLIENT_HAS_SEVERE_DPD_HISTORY': 0,
                'CLIENT_HAS_ANY_DPD_HISTORY': 0,
            }

        # Normalize numeric fields and compute bureau-level aggregates
        credit_types = set()
        active_cnt = closed_cnt = bad_debt_cnt = sold_cnt = 0
        overdue_days_sum = 0
        overdue_days_max = None
        overdue_cnt = 0

        amt_overdue_sum = 0.0
        amt_overdue_max = None
        amt_max_overdue_ever = None
        amt_overdue_cnt = 0

        prolong_sum = 0
        prolong_max = None
        prolong_cnt = 0

        sum_debt = 0.0
        sum_limit = 0.0
        sum_total_credit = 0.0

        sum_debt_active = 0.0
        sum_limit_active = 0.0
        sum_total_credit_active = 0.0

        maxed_out_cnt = 0
        high_util_cnt = 0

        for rec in bureau:
            credit_types.add(rec.get('credit_type'))
            status = rec.get('credit_active')
            if status == 'Active':
                active_cnt += 1
            elif status == 'Closed':
                closed_cnt += 1
            elif status == 'Bad debt':
                bad_debt_cnt += 1
            elif status == 'Sold':
                sold_cnt += 1

            day_overdue = to_int(rec.get('credit_day_overdue'))
            if day_overdue is not None:
                overdue_days_sum += day_overdue
                overdue_cnt += 1 if day_overdue > 0 else 0
                overdue_days_max = day_overdue if overdue_days_max is None else max(overdue_days_max, day_overdue)

            amt_overdue = to_float(rec.get('amt_credit_sum_overdue')) or 0.0
            amt_overdue_sum += amt_overdue
            if amt_overdue > 0:
                amt_overdue_cnt += 1
            amt_overdue_max = amt_overdue if amt_overdue_max is None else max(amt_overdue_max, amt_overdue)

            amt_max_overdue = to_float(rec.get('amt_credit_max_overdue'))
            if amt_max_overdue is not None:
                amt_max_overdue_ever = amt_max_overdue if amt_max_overdue_ever is None else max(amt_max_overdue_ever, amt_max_overdue)

            prolong = to_int(rec.get('cnt_credit_prolong'))
            if prolong is not None:
                prolong_sum += prolong
                prolong_max = prolong if prolong_max is None else max(prolong_max, prolong)
                if prolong > 0:
                    prolong_cnt += 1

            debt = to_float(rec.get('amt_credit_sum_debt')) or 0.0
            limit_ = to_float(rec.get('amt_credit_sum_limit')) or 0.0
            total_credit = to_float(rec.get('amt_credit_sum')) or 0.0
            sum_debt += debt
            sum_limit += limit_
            sum_total_credit += total_credit

            if status == 'Active':
                sum_debt_active += debt
                sum_limit_active += limit_
                sum_total_credit_active += total_credit

            if limit_ is not None and limit_ > 0:
                if debt >= limit_:
                    maxed_out_cnt += 1
                if debt > 0.8 * limit_:
                    high_util_cnt += 1

        # Means
        overdue_days_mean = safe_div(overdue_days_sum, total)
        amt_overdue_mean = safe_div(amt_overdue_sum, total)
        prolong_mean = safe_div(prolong_sum, total)

        # Ratios (bureau-level)
        bad_debt_ratio = safe_div(bad_debt_cnt, total)
        sold_ratio = safe_div(sold_cnt, total)
        high_risk_ratio = safe_div(bad_debt_cnt + sold_cnt, total)
        overdue_ratio = safe_div(overdue_cnt, total)
        amt_overdue_ratio = safe_div(amt_overdue_cnt, total)
        prolong_ratio = safe_div(prolong_cnt, total)
        util_ratio = safe_div(sum_debt, sum_limit)
        debt_to_credit_ratio = safe_div(sum_debt, sum_total_credit)
        overdue_to_credit_ratio = safe_div(amt_overdue_sum, sum_total_credit)
        active_util_ratio = safe_div(sum_debt_active, sum_limit_active)
        maxed_out_ratio = safe_div(maxed_out_cnt, total)
        high_util_ratio = safe_div(high_util_cnt, total)

        # bureau_balance aggregation per SK_ID_BUREAU
        # Keep only balances that belong to the bureau records we have
        bureau_ids = {rec.get('sk_id_bureau') for rec in bureau if rec.get('sk_id_bureau') is not None}
        bb_per_bureau: Dict[Any, Dict[str, Any]] = {}
        for row in balance:
            sk_b = row.get('sk_id_bureau')
            if sk_b not in bureau_ids:
                continue
            entry = bb_per_bureau.setdefault(sk_b, {
                'total_months': 0,
                'months_on_time': 0,
                'months_closed': 0,
                'months_unknown': 0,
                'dpd_1_30': 0,
                'dpd_31_60': 0,
                'dpd_61_90': 0,
                'dpd_91_120': 0,
                'dpd_120_plus': 0,
                'earliest': None,
                'latest': None,
            })
            entry['total_months'] += 1
            status = (row.get('status') or '').upper()
            if status == '0':
                entry['months_on_time'] += 1
            elif status == 'C':
                entry['months_closed'] += 1
            elif status == 'X':
                entry['months_unknown'] += 1
            elif status == '1':
                entry['dpd_1_30'] += 1
            elif status == '2':
                entry['dpd_31_60'] += 1
            elif status == '3':
                entry['dpd_61_90'] += 1
            elif status == '4':
                entry['dpd_91_120'] += 1
            elif status == '5':
                entry['dpd_120_plus'] += 1

            mb = to_int(row.get('months_balance'))
            if mb is not None:
                entry['earliest'] = mb if entry['earliest'] is None else min(entry['earliest'], mb)
                entry['latest'] = mb if entry['latest'] is None else max(entry['latest'], mb)

        # Roll up per-bureau metrics to client-level
        bb_count = len(bb_per_bureau)
        total_months_all = 0
        total_months_on_time = 0
        total_dpd_all = 0
        total_severe_dpd_months = 0

        worst_dpd_ratio = None
        worst_severe_dpd_ratio = None
        worst_on_time_ratio = None
        avg_dpd_ratio_acc = 0.0
        avg_on_time_ratio_acc = 0.0
        ratio_count = 0

        count_bureaus_with_severe = 0
        count_bureaus_with_any = 0

        for entry in bb_per_bureau.values():
            tm = entry['total_months']
            on_time = entry['months_on_time']
            dpd_total = entry['dpd_1_30'] + entry['dpd_31_60'] + entry['dpd_61_90'] + entry['dpd_91_120'] + entry['dpd_120_plus']
            severe = entry['dpd_120_plus']

            total_months_all += tm
            total_months_on_time += on_time
            total_dpd_all += dpd_total
            total_severe_dpd_months += severe

            dpd_ratio = safe_div(dpd_total, tm)
            severe_ratio = safe_div(severe, tm)
            on_time_ratio = safe_div(on_time, tm)

            if dpd_ratio is not None:
                worst_dpd_ratio = dpd_ratio if worst_dpd_ratio is None else max(worst_dpd_ratio, dpd_ratio)
            if severe_ratio is not None:
                worst_severe_dpd_ratio = severe_ratio if worst_severe_dpd_ratio is None else max(worst_severe_dpd_ratio, severe_ratio)
            if on_time_ratio is not None:
                worst_on_time_ratio = on_time_ratio if worst_on_time_ratio is None else min(worst_on_time_ratio, on_time_ratio)

            if dpd_ratio is not None and on_time_ratio is not None:
                avg_dpd_ratio_acc += dpd_ratio
                avg_on_time_ratio_acc += on_time_ratio
                ratio_count += 1

            if severe > 0:
                count_bureaus_with_severe += 1
            if dpd_total > 0:
                count_bureaus_with_any += 1

        avg_dpd_ratio = safe_div(avg_dpd_ratio_acc, ratio_count)
        avg_on_time_ratio = safe_div(avg_on_time_ratio_acc, ratio_count)

        overall_on_time_ratio = safe_div(total_months_on_time, total_months_all)
        overall_dpd_ratio = safe_div(total_dpd_all, total_months_all)
        overall_severe_dpd_ratio = safe_div(total_severe_dpd_months, total_months_all)

        # Assemble final feature dict
        features = {
            'BUREAU_TOTAL_COUNT': total,
            'BUREAU_CREDIT_TYPES_COUNT': len(credit_types),
            'BUREAU_ACTIVE_COUNT': active_cnt,
            'BUREAU_CLOSED_COUNT': closed_cnt,
            'BUREAU_BAD_DEBT_COUNT': bad_debt_cnt,
            'BUREAU_SOLD_COUNT': sold_cnt,
            'BUREAU_BAD_DEBT_RATIO': bad_debt_ratio,
            'BUREAU_SOLD_RATIO': sold_ratio,
            'BUREAU_HIGH_RISK_RATIO': high_risk_ratio,
            'BUREAU_OVERDUE_DAYS_TOTAL': overdue_days_sum,
            'BUREAU_OVERDUE_DAYS_MEAN': overdue_days_mean,
            'BUREAU_OVERDUE_DAYS_MAX': overdue_days_max,
            'BUREAU_OVERDUE_COUNT': overdue_cnt,
            'BUREAU_OVERDUE_RATIO': overdue_ratio,
            'BUREAU_AMT_OVERDUE_TOTAL': amt_overdue_sum,
            'BUREAU_AMT_OVERDUE_MEAN': amt_overdue_mean,
            'BUREAU_AMT_OVERDUE_MAX': amt_overdue_max,
            'BUREAU_AMT_MAX_OVERDUE_EVER': amt_max_overdue_ever,
            'BUREAU_AMT_OVERDUE_COUNT': amt_overdue_cnt,
            'BUREAU_AMT_OVERDUE_RATIO': amt_overdue_ratio,
            'BUREAU_PROLONG_TOTAL': prolong_sum,
            'BUREAU_PROLONG_MEAN': prolong_mean,
            'BUREAU_PROLONG_MAX': prolong_max,
            'BUREAU_PROLONG_COUNT': prolong_cnt,
            'BUREAU_PROLONG_RATIO': prolong_ratio,
            'BUREAU_CREDIT_UTILIZATION_RATIO': util_ratio,
            'BUREAU_DEBT_TO_CREDIT_RATIO': debt_to_credit_ratio,
            'BUREAU_OVERDUE_TO_CREDIT_RATIO': overdue_to_credit_ratio,
            'BUREAU_ACTIVE_CREDIT_SUM': sum_total_credit_active,
            'BUREAU_ACTIVE_DEBT_SUM': sum_debt_active,
        }

        # Compute overdue sum for active credits
        sum_overdue_active = 0.0
        for rec in bureau:
            if rec.get('credit_active') == 'Active':
                sum_overdue_active += to_float(rec.get('amt_credit_sum_overdue')) or 0.0
        features['BUREAU_ACTIVE_OVERDUE_SUM'] = sum_overdue_active

        features.update({
            'BUREAU_ACTIVE_UTILIZATION_RATIO': active_util_ratio,
            'BUREAU_MAXED_OUT_COUNT': maxed_out_cnt,
            'BUREAU_MAXED_OUT_RATIO': maxed_out_ratio,
            'BUREAU_HIGH_UTIL_COUNT': high_util_cnt,
            'BUREAU_HIGH_UTIL_RATIO': high_util_ratio,
            'BUREAU_WITH_BALANCE_COUNT': bb_count,
            'TOTAL_MONTHS_ALL_BUREAUS': total_months_all,
            'TOTAL_MONTHS_ON_TIME': total_months_on_time,
            'TOTAL_DPD_ALL_BUREAUS': total_dpd_all,
            'TOTAL_SEVERE_DPD_MONTHS': total_severe_dpd_months,
            'WORST_DPD_RATIO': worst_dpd_ratio,
            'WORST_SEVERE_DPD_RATIO': worst_severe_dpd_ratio,
            'WORST_ON_TIME_RATIO': worst_on_time_ratio,
            'AVG_DPD_RATIO': avg_dpd_ratio,
            'AVG_ON_TIME_RATIO': avg_on_time_ratio,
            'COUNT_BUREAUS_WITH_SEVERE_DPD': count_bureaus_with_severe,
            'COUNT_BUREAUS_WITH_ANY_DPD': count_bureaus_with_any,
            'OVERALL_ON_TIME_RATIO': overall_on_time_ratio,
            'OVERALL_DPD_RATIO': overall_dpd_ratio,
            'OVERALL_SEVERE_DPD_RATIO': overall_severe_dpd_ratio,
            'CLIENT_HAS_SEVERE_DPD_HISTORY': 1 if count_bureaus_with_severe > 0 else 0,
            'CLIENT_HAS_ANY_DPD_HISTORY': 1 if count_bureaus_with_any > 0 else 0,
        })

        return features

    def _extract_sk_id_curr_from_cdc(self, cdc_message: Dict[str, Any]) -> Optional[str]:
        """Extract sk_id_curr from CDC message.

        Supports plain messages and Debezium envelope with payload.before/after.
        """
        try:
            message = cdc_message or {}
            # Debezium JSON typically nests in payload
            if isinstance(message.get("payload"), dict):
                message = message["payload"]

            # Prefer 'after' (create/update), fallback to 'before' (delete)
            if isinstance(message.get("after"), dict):
                rec = message["after"]
            elif isinstance(message.get("before"), dict):
                rec = message["before"]
            else:
                rec = message

            # Sometimes another layer (e.g., value field)
            if isinstance(rec, dict) and "sk_id_curr" in rec:
                return str(rec["sk_id_curr"])
            if isinstance(rec, dict) and isinstance(rec.get("value"), dict) and "sk_id_curr" in rec["value"]:
                return str(rec["value"]["sk_id_curr"])

            # Log a concise preview for troubleshooting
            logger.debug({
                "cdc_keys": list(cdc_message.keys()) if isinstance(cdc_message, dict) else type(cdc_message).__name__,
                "payload_keys": list((cdc_message.get("payload") or {}).keys()) if isinstance(cdc_message, dict) and isinstance(cdc_message.get("payload"), dict) else None
            })
            return None
        except Exception as e:
            logger.error(f"Error extracting sk_id_curr from CDC: {e}")
            return None

    async def run(self):
        """Main service loop."""
        logger.info("Starting External Bureau Service...")
        
        try:
            self.consumer.subscribe([self.source_topic])
            
            while True:
                msg = self.consumer.poll(timeout=1.0)
                
                if msg is None:
                    continue
                    
                if msg.error():
                    logger.error(f"Consumer error: {msg.error()}")
                    continue
                
                try:
                    # Parse CDC message
                    cdc_data = json.loads(msg.value().decode('utf-8'))
                    sk_id_curr = self._extract_sk_id_curr_from_cdc(cdc_data)
                    
                    if not sk_id_curr:
                        logger.warning("Could not extract sk_id_curr from CDC message")
                        continue
                    
                    # Process external bureau data
                    external_features = await self.process_loan_application(sk_id_curr)
                    
                    if external_features:
                        # Publish to external features topic
                        self.producer.produce(
                            topic=self.sink_topic,
                            key=str(sk_id_curr).encode('utf-8'),
                            value=json.dumps(external_features).encode('utf-8'),
                            callback=self._delivery_callback
                        )
                        self.producer.poll(0)  # Non-blocking
                    
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse CDC message: {e}")
                except Exception as e:
                    logger.error(f"Error processing message: {e}")
                    
        except KeyboardInterrupt:
            logger.info("Shutting down External Bureau Service...")
        finally:
            self.consumer.close()
            self.producer.flush()

    def _delivery_callback(self, err, msg):
        """Callback for message delivery confirmation."""
        if err is not None:
            logger.error(f'Message delivery failed: {err}')
        else:
            logger.debug(f'Message delivered to {msg.topic()} [{msg.partition()}] at offset {msg.offset()}')


async def main():
    service = ExternalBureauService()
    await service.run()


if __name__ == "__main__":
    asyncio.run(main())
