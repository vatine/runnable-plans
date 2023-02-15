# runnable-plans
A half-measure between "this recurring task is documented on a page somewhere" and "this recurring task is automated"

## Rationale

Automating recurring tasks is good. Being able to resume an automated task from a failure point is good.

What runnable-plans provide is a middle ground between "we know what steps need to be done" and "yep, this is now something we can 100% delegate to a machine". It provides the ability to:

 * Specify variables (at the moment, only from stdin)
 * Declare action dependency ("X must be completed before Y is completed")
 * Stop once no further progress can be made (all remaining actions have at least one required precursor that has failed)
 * Resume execution of a plan (failed or interrupted), to allow for manual fixing of a failed step (or plan modification).
 * Generate a graph of a plan (or a save-state), for visual inspection

Partially for "you should know your dependencies" and partially for "well, at some point, we may want to extend the runner to do things in parallel", there is no inherent sequencing within a plan. All sequencing has to be done by declaring dependencies. Any specific action can depend on any number of existing actions. Multiple actions can have a dependency on a single action.

## Good reasons to reach for this tool

You have one, or more, processes that require multiple steps, documented as a sequential list of operations and at least SOME of those steps should be automatable.

At this point, you can turn that documented list into somewhat-executable code in version control. It can start as a sequence of "get some input" and "prompt people to perform actions manually".
