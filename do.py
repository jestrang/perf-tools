#!/usr/bin/env python2
# Misc utilities for CPU performance analysis on Linux
# Author: Ahmad Yasin
# edited: Jan. 2021
# TODO list:
#   add trials support
#   re-enable power in system-wide (kernel support is missing for ICL+ models)
#   convert verbose to a bitmask
#   add test command to gate commits to this file
#   check sudo permissions
#   auto-produce options for 'command' help
__author__ = 'ayasin'

import argparse
import common as C
from os import getpid

do = {'run':        './run.sh',
  'info-metrics':   "--nodes '+CoreIPC,+Instructions,+CORE_CLKS,+IpTB,+UPI,+CPU_Utilization,+Time,+MUX'",
  'extra-metrics':  "--metric-group +Summary,+HPC --nodes +Mispredictions,+IpTB,+BpTkBranch,+IpCall,+IpLoad",
  'super': 0,
  'toplev-levels':  3,
  'perf-stat-def':  'cpu-clock,context-switches,cpu-migrations,page-faults,cycles,instructions,branches,branch-misses',
  'perf-record':    '', #'-e BR_INST_RETIRED.NEAR_CALL:pp ',
  'gen-kernel':     1,
  'compiler':       'gcc', #~/tools/llvm-6.0.0/bin/clang',
  'cmds_file':      None,
}
args = []

def exe(x, msg=None, redir_out=' 2>&1'):
  do['cmds_file'].write(x + '\n')
  return C.exe_cmd(x, msg, redir_out, args.verbose>0)
def exe_to_null(x): return exe(x + ' > /dev/null', redir_out=None)
def exe_v0(x='true', msg=None): return C.exe_cmd(x, msg)

def uniq_name():
  if args.app_name is None: return 'run%d'%getpid()
  name = args.app_name.split(' ')[2:] if 'taskset' in args.app_name.split(' ')[0] else args.app_name.split(' ')
  if '/' in name[0]: name[0] = name[0].split('/')[-1].replace('.sh', '')
  name = ''.join(name)
  name = name.replace('/tmp', '-')
  return C.chop(name, './~')

def tools_install(installer='sudo apt-get install '):
  for x in ('numactl', 'dmidecode'):
    exe(installer + x, 'installing ' + x)
  if do['super']: exe('./build-xed.sh', 'installing xed')

def tools_update():
  exe('git pull')
  exe('git checkout HEAD run.sh')
  exe('git submodule update --remote')
  if do['super']: exe(args.pmu_tools + "/event_download.py") # requires sudo

def setup_perf(actions=('set', 'log'), out=None):
  def set_it(p, v): exe_to_null('echo %d | sudo tee %s'%(v, p))
  TIME_MAX = '/proc/sys/kernel/perf_cpu_time_max_percent'
  perf_params = [
    ('/proc/sys/kernel/nmi_watchdog', 0, ),
    ('/proc/sys/kernel/soft_watchdog', 0, ),
    ('/proc/sys/kernel/kptr_restrict', 0, ),
    ('/proc/sys/kernel/perf_event_paranoid', -1, ),
    ('/proc/sys/kernel/perf_event_mlock_kb', 60000, ),
    ('/proc/sys/kernel/perf_event_max_sample_rate', int(1e9), 1),
    ('/sys/devices/cpu/perf_event_mux_interval_ms', 100, ),
  ]
  if 'set' in actions: exe_v0(msg='setting up perf')
  superv = 'sup' in actions or do['super']
  if superv:
    set_it(TIME_MAX, 25)
    perf_params += [('/sys/devices/cpu/rdpmc', 1, ),
      ('/sys/bus/event_source/devices/cpu/rdpmc', 2, )]
  perf_params += [(TIME_MAX, 0, 1)] # has to be last
  for x in perf_params: 
    if (len(x) is 2) or superv:
      param, value = x[0], x[1]
      if 'set' in actions: set_it(param, value)
      if 'log' in actions: exe_v0('printf "%s : %s \n"'%(param, C.file2str(param)) + 
                                  (' >> %s'%out if out != None else ''))

def smt(x='off'):
  exe('echo %s | sudo tee /sys/devices/system/cpu/smt/control'%x)

def log_setup(out = 'setup-system.log'):
  def new_line(): exe_v0('echo >> %s'%out)
  exe('lscpu > setup-lscpu.log', 'logging setup')
  
  exe('uname -a > ' + out)
  exe('cat /etc/os-release | grep -v URL >> ' + out)
  new_line()
  exe('%s --version >> '%args.perf + out)
  setup_perf('log', out)
  new_line()
  #exe('cat /etc/lsb-release >> ' + out)
  exe('numactl -H >> ' + out)
  
  if do['super']: exe('sudo dmidecode > setup-memory.log')

def profile(log=False, out='run'):
  def en(n): return int(args.profile_mask, 16) & 2**n
  out = uniq_name()
  perf=args.perf
  r = do['run']
  if en(0) or log: log_setup()
  
  def power(rapl=['pkg', 'cores', 'ram'], px='/,power/energy-'): return px[2:] + px.join(rapl) + '/'
  def perf_e(): return '-e %s,%s'%(do['perf-stat-def'], power()) if do['super'] else ''
  def perf_stat(flags=''): return '%s stat %s -- %s | tee %s.perf_stat%s.log | egrep "seconds|CPUs|GHz|insn|pkg"'%(perf, flags, r, out, flags.split(' ')[0])
  if en(1): exe(perf_stat(), 'per-app counting')
  if en(2): exe(perf_stat('-a ' + perf_e()), 'system-wide counting')

  if en(3):
    base = out+'.perf'
    if do['perf-record']: base += C.chop(do['perf-record'], ' :')
    exe(perf + ' record -g '+do['perf-record']+r, 'sampling %sw/ stacks'%do['perf-record'])
    exe(perf + " report --stdio --hierarchy --header | grep -v ' 0\.0.%' | tee "+base+"-modules.log " \
      "| grep -A11 Overhead", '@report modules')
    base2 = base+'-code'
    exe(perf + " annotate --stdio | c++filt | tee " + base2 + ".log" \
      "| egrep -v -E ' 0\.[0-9][0-9] :|^\s+:($|\s+(Disassembly of section .text:|//|#include))' " \
      "| tee " + base2 + "_nonzero.log > /dev/null " \
      "&& egrep -n -B1 ' ([1-9].| [1-9])\... :|\-\-\-' " + base2 + ".log | grep '^[1-9]' " \
      "| head -20", '@annotate code', '2>/dev/null')
  
  toplev = '' if perf is 'perf' else 'PERF=%s '%perf
  toplev+= (args.pmu_tools + '/toplev.py --no-desc %s'%do['info-metrics'])
  grep_bk= "egrep '<==|MUX|Info.Bott'"
  grep_nz= "egrep -v '(FE|BE|BAD|RET).*[ \-][10]\.. |^RUN|not found' "
  def toplev_V(v, tag=''):
    o = '%s.toplev%s.log'%(out, v.split()[0]+tag)
    return '%s %s -V %s -- %s'%(toplev, v, o.replace('.log', '-perf.csv'), r), o
  
  cmd, log = toplev_V('-vl6')
  if en(4): exe(cmd + ' | tee %s | %s'%(log, grep_bk), 'topdown full')
  
  cmd, log = toplev_V('-vl%d'%do['toplev-levels'])
  if en(5): exe(cmd + ' | tee %s | %s'%(log, grep_nz), 'topdown %d-levels'%do['toplev-levels'])
  
  cmd, log = toplev_V('--drilldown')# --show-sample')
  if en(6): exe(cmd + ' | tee %s | egrep -v "^(Run toplev|Adding|Using)" '%log, 'topdown auto-drilldown')
  
  if en(7) and args.no_multiplex:
    cmd, log = toplev_V('-vl6 %s --no-multiplex '%do['extra-metrics'], '-nomux')
    exe(cmd + " | tee %s | %s"%(log, grep_nz)
      #'| grep ' + ('RUN ' if args.verbose > 1 else 'Using ') + out +# toplev misses stdout.flush() as of now :(
      , 'topdown full no multiplexing')

def alias(cmd, log_files=['','log','csv']):
  if cmd == 'tar': exe('tar -czvf results.tar.gz run.sh '+ ' *.'.join(log_files) + ' .*.cmd')
  if cmd == 'clean': exe('rm -f ' + ' *.'.join(log_files + ['pyc']) + ' *perf.data* results.tar.gz ')

def build_kernel(dir='./kernels/'):
  def fixup(x): return x.replace('./', dir)
  app = args.app_name
  if do['gen-kernel']:
    exe(fixup('./gen-kernel.py %s > ./%s.c'%(args.gen_args, app)), 'building kernel: ' + app)
    if args.verbose > 3: exe(fixup('head -2 ./%s.c'%app))
  exe(fixup('%s -g -O2 -o ./%s ./%s.c'%(do['compiler'], app, app)), None if do['gen-kernel'] else 'compiling')
  do['run'] = fixup('taskset 0x4 ./%s %d'%(app, int(float(args.app_iterations))))

def parse_args():
  ap = argparse.ArgumentParser()
  ap.add_argument('command', nargs='+', help='supported options: ' \
      'setup-perf log profile tar, all (for these 4)' \
      '\n\t\t\tbuild [disable|enable]-smt setup-all tools-update')
  ap.add_argument('--perf', default='perf', help='use a custom perf tool')
  ap.add_argument('--pmu-tools', default='./pmu-tools', help='use a custom pmu-tools directory')
  ap.add_argument('-g', '--gen-args', help='args to gen-kernel.py')
  ap.add_argument('-a', '--app-name', default=None, help='name of kernel')
  ap.add_argument('-ki', '--app-iterations', default='1e9', help='num-iterations of kernel')
  ap.add_argument('-pm', '--profile-mask', default='FF', help='mask to control stage in profile-command')
  ap.add_argument('-N', '--no-multiplex', action='store_const', const=False, default=True,
    help='skip no-multiplexing reruns')
  ap.add_argument('-v', '--verbose', type=int, help='verbose level; 0:none, 1:commands, ' \
    '2:+verbose-on-metrics, 3:+event-groups, 4:ALL')
  x = ap.parse_args()
  return x

def main():
  global args
  args = parse_args()
  if args.verbose > 3: print args
  if args.verbose > 2: do['info-metrics'] = do['info-metrics'] + ' -g'
  if args.verbose > 1: do['info-metrics'] = do['info-metrics'] + ' -v'
  if args.app_name: do['run'] = args.app_name
  
  do['cmds_file'] = open('.%s.cmd'%uniq_name(), 'w')
  
  for c in args.command:
    if   c == 'forgive-me':   pass
    elif c == 'setup-all':
      tools_install()
      setup_perf()
    elif c == 'setup-perf':   setup_perf()
    elif c == 'tools-update': tools_update()
    elif c == 'disable-smt':  smt()
    elif c == 'enable-smt':   smt('on')
    elif c == 'log':          log_setup()
    elif c == 'profile':      profile()
    elif c == 'tar':          alias(c)
    elif c == 'clean':        alias(c)
    elif c == 'all':
      setup_perf()
      profile(True)
      alias('tar')
    elif c == 'build':        build_kernel()
    else:
      C.error("Unknown command: '%s' !"%c)
      return -1
  return 0

if __name__ == "__main__":
  main()
  do['cmds_file'].close()

