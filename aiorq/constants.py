default_queue_name = 'aiorq:queue'
default_worker_name = "pai"
job_key_prefix = 'aiorq:job:'
in_progress_key_prefix = 'aiorq:in-progress:'
result_key_prefix = 'aiorq:result:'
retry_key_prefix = 'aiorq:retry:'
abort_jobs_ss = 'aiorq:abort'
# age of items in the abort_key sorted set after which they're deleted
abort_job_max_age = 60
health_check_key_suffix = 'aiorq:health-check:'
# how long to keep the "in_progress" key after a cron job ends to prevent the job duplication
# this can be a long time since each cron job has an ID that is unique for the intended execution time
keep_cronjob_progress = 60

time_zone = 'Asia/Shanghai'

# worker_key task_key in redis
worker_key = "aiorq:worker"
task_key = "aiorq:task"

# how long to keep the worker_key_close_expire key
worker_key_close_expire = 3
