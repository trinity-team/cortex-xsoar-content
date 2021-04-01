from CommonServerPython import *


# Cortex Data Lake PAN-OS log monitoring monitoring
# PRE_REQUISITE: Enable Cortex Data Lake integration and/or PAN-OS integration (if the automated creation of a FW list is expected)

def check_instance(all_instances: list, integration_name: str, err_msg: str):
    """
    :param all_instances: All integration instances in the platform.
    :param integration_name: integration brand name
    :param err_msg: error message string
    """
    instance_found_active: bool = False
    for instance in all_instances:
        if all_instances[instance]['brand'] == integration_name and all_instances[instance]['state'] == 'active':
            instance_found_active = True
            break
    if not instance_found_active:
        raise Exception(err_msg)


def get_firewall_serials(pan_os_instance_name: str) -> list:
    """
    :param pan_os_instance_name: Name of the instance of the PAN-OS integration.
    :return: List of the FWs serials associated with this instance.
    """
    fw_monitor_list: list = []
    fw_query = {'type': 'op', 'cmd': '<show><devices><all></all></devices></show>', 'raw-response': 'true',
                'using': pan_os_instance_name}
    fw_query_result = demisto.executeCommand("panorama", fw_query)
    if fw_query_result and isinstance(fw_query_result, list):
        for fw in fw_query_result[0]['Contents']['response']['result']['devices']['entry']:
            fw_monitor_list.append(fw['serial'])
    else:
        raise Exception(
            "Failed to retrieve Firewalls list from PAn-OS, try to specify manually a list of serials.")

    return fw_monitor_list


def query_cdl(fw_monitor_list: list) -> CommandResults:
    """
    :param fw_monitor_list: list of FWs serials
    :return: CommandResults object containing the serials which sent logs and that did not.
    """
    no_logs_str = "### Logs traffic table\n**No entries.**\n"
    firewalls_with_logs = []
    firewalls_without_logs = []
    start_time = datetime.datetime.utcnow() - datetime.timedelta(hours=12)  # Looking for the last 12 hours of logs
    start_time = start_time.strftime('%Y-%m-%d %H:%M:%S')
    query = {'fields': 'all', 'time_range': '1 day', 'limit': str(1), 'start_time': start_time}
    for current_fw in fw_monitor_list:
        if len(current_fw) not in (12, 15):  # VM serial are 15 digits and FW serial are 12 digits
            raise Exception(f'{current_fw} - incorrect Firewall serial format.')
        query['query'] = f'log_source_id = \'{current_fw}\''
        query_result = demisto.executeCommand("cdl-query-traffic-logs", query)

        if query_result:
            if query_result[0]['HumanReadable'] == no_logs_str:
                firewalls_with_logs.append(current_fw)
            else:
                firewalls_without_logs.append(current_fw)

    all_results = [{'FirewallsWithLogsSent': firewalls_with_logs,
                    'FirewallsWithoutLogsSent': firewalls_without_logs}]

    return CommandResults(
        outputs_prefix='CDL.monitoring',
        outputs_key_field=['FirewallsWithLogsSent', 'FirewallsWithoutLogsSent'],
        ignore_auto_extract=True,
        outputs=all_results
    )


def main():
    try:
        args = demisto.args()
        all_instances = demisto.getModules()  # Gather existing instances

        # Look for active Cortex Data Lake instance
        check_instance(all_instances, "Cortex Data Lake",
                       "No active Cortex Data Lake integration found, please configure one.")

        # The Firewall list must be a comma-separated list of FW serials
        fw_monitor_list = argToList(args.get('fw_serials'))
        if not fw_monitor_list:  # List of FW to monitor is empty, get it from Panorama
            pan_os_integration_name = args.get('pan_os_integration_name', 'Panorama')
            if not pan_os_integration_name:
                raise Exception("A Firewall serial list or a PAN-OS integration name is needed(default is Panorama).")
            # Look for active PAN-OS instance
            check_instance(all_instances, pan_os_integration_name,
                           f'Integration instance {pan_os_integration_name} is not active or is not a PAN-OS integration.')
            # Get FW serials
            fw_monitor_list = get_firewall_serials(fw_monitor_list, pan_os_integration_name)

        # Log the list of firewalls to be monitored
        demisto.debug(f'List of FW serials: {fw_monitor_list}')
        return_results(query_cdl(fw_monitor_list))

    except Exception as err:
        return_error(str(err), err)


if __name__ in ('__main__', '__builtin__', 'builtins'):
    main()
