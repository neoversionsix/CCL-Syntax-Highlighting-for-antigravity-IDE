; This is a sample CCL program
declare my_var = f8 with noconstant(0.0)

select into "nl:"
    p.person_id,
    p.name_full_formatted
from
    person p
where p.active_ind = 1
with format, separator=" ", time=60

if (my_var = 1.0)
    ; do something
    update into person p
    set p.active_ind = 0
    where p.person_id = 12345
endif
