create or replace view bureau_data as 
select b.*, bb.status, bb.months_balance
from bureau b left join bureau_balance bb on b.sk_id_bureau = bb.sk_id_bureau;


create or replace view previous_application_data as 


select pa.*, pcb.months_balance, pcb.cnt_instalment , pcb.cnt_instalment_future, pcb.months_balance, pcb.name_contract_status,
		ip.amt_instalment , ip.amt_payment ,ip.
from previous_application pa 
	left join pos_cash_balance pcb on pa.sk_id_prev = pcb.sk_id_prev 
	left join installments_payments ip on pa.sk_id_prev = ip.sk_id_prev 
	left join credit_card_balance ccb on pa.sk_id_prev = ccb.sk_id_prev 