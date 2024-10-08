import json
from typing import Optional, Dict
from enhancifai_backend.database.handlers.runs import RunsDbCore

class RunsProgress:
    def __init__(self):
        # Initialization can remain empty if all data is stored in DB
        pass

    def add_run(self, run_id: int, total_rows: int):
        """
        Adds a new run to the database with initial details.
        """
        run_details = {
            'total_rows': total_rows,
            'rows_processed': 0,
            'status': 'new',
            'details': {}
        }
        RunsDbCore.insert_run_details(run_id, json.dumps(run_details))

    def update_progress(self, run_id: int, rows_processed: int):
        """
        Updates the progress of a specific run.
        """
        run_details = RunsDbCore.get_run_details(run_id)['run_details']
        if RunsDbCore.is_run_cancelled(run_id):
            run_details['status'] = 'cancelled'
        else:
            run_details['status'] = 'pending'
        run_details['rows_processed'] = rows_processed
        
        RunsDbCore.insert_run_details(run_id, json.dumps(run_details))

    def update_details(self, run_id: int, details: Dict):
        """
        Updates the details of a specific run.
        """
        run_details = RunsDbCore.get_run_details(run_id)['run_details']
        run_details['details'] = details
        
        if run_details['status'] != 'completed' and RunsDbCore.is_run_cancelled(run_id) is False:
            run_details['status'] = 'completed'
        
        RunsDbCore.insert_run_details(run_id, json.dumps(run_details))

    def check_status(self, run_id: int) -> Optional[Dict]:
        """
        Checks the status of a specific run.
        """
        _run_details = RunsDbCore.get_run_details(run_id)
        
        if _run_details is not None:
            run_details = _run_details['run_details']
            #print(run_details)
            if RunsDbCore.is_run_cancelled(run_id):
                return {'status': 'cancelled'}
            if run_details['status'] == 'completed':
                response = run_details['details']
                response['status'] = 'completed'
                return response
            elif run_details['rows_processed'] > 0:
                if run_details['rows_processed'] >= run_details['total_rows']:
                    response = run_details['details']
                    response['status'] = 'completed'
                    return response
                percentage = (run_details['rows_processed'] / run_details['total_rows']) * 100
                return {'status': 'pending', 'progress': f"{percentage:.0f}", 'remark': f"{percentage:.0f}% completed."}
            else:
                return {'status': run_details['status']}
        return None


runs_progress = RunsProgress()
