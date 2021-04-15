# perf-tools
A collection of performance analysis tools, recipes &amp; more

## Overview
* **do.py** -- handy shortcuts for setting up and doing profiling, over [Linux perf](https://perf.wiki.kernel.org/index).
* **kernels/** -- an evolving collection of x86 kernels
  * **gen-kernel.py** -- generator of X86 kernels
  * **jumpy.py** -- module for different jumping constructs
  * **peak4wide.c** -- a sample kernel for 4-wide superscalar machine, e.g. Skylake
* **pmu-tools/** -- linked Andi Kleen's perf-based great tools
  * **toplev** -- profiler featuring the [Top-down Microarchitecture Analysis](http://bit.ly/tma-ispass14) (TMA) method on Intel processors
  * **ocperf** -- perf wrappers that converts Intel event names to perf-events syntax  
### Checkout with: 
`git clone --recurse-submodules https://github.com/aayasin/perf-tools`


## Usage:
### setting up your system
* to setup the perf tool, invoke `./do.py setup-perf`
* to turn-off SMT (CPU hyper-threading), invoke `./do.py disable-smt`; don't forget to re-enable it once done, e.g. `./do.py enable-smt`

### profiling
First, edit `run.sh` to invoke your application or use the `-a '<your app and args>'`, alternatively.
* to profile, simply `./do.py profile` which includes multiple steps:
  * **basic counting & sampling** steps: collect key metrics like time or CPUs utilized,
    do basic profiling and output top CPU-time consuming commands/modules/functions as well as
    the source/disassembly for top function(s).
  * **topdown profiling** steps: collect reduced tree, auto drill-down and full collections with multiple reruns. 
  A filtered output will be dumped on screen
    while all logs are saved to the current directory.
  * Use `--profile-mask 42`, as an example, to invoke subset of all steps,
    or `-N` to disable the step with re-runs. 
* `./do.py log` will log hardware and software setup.
* `./do.py log profile` will do the previous two steps.
* `./do.py tar` will archive all logs into a shareable tar file.
* `./do.py all` will setup perf before doing all above profiling steps.

### kernels (microbenchmarks)
* to build pre-defined ones, simply `cd kernels/ && ./build.sh`
* to run a kernel, invoke it with number-of-iterations, e.g.
`    ./kernels/jumpy5p14 200000000`
* to create a custom kernel, set the desired parameters. e.g.
`    ./kernels/gen-kernel.py -i PAUSE -n 10`
  outputs a C-file of a loop with 10 PAUSE instructions, that can be fed to your favorite compiler.
