; This is a sample CCL program
! Exclamation-mark comments are also supported in CCL
%i cclsource:demo_include.inc

drop program sample_ccl:dba go
create program sample_ccl:dba

/*
 * Record structure & variable declarations
 */
free record rs_dta_results
record rs_dta_results (
    1 cnt = i4
    1 list[*]
        2 clean_text = vc
        2 flag = c1
) with protect

declare my_var = f8 with protect, noconstant(0.0)
declare raw_text_var = vc with protect, noconstant("")
declare valid_output_cnt = i4 with protect, noconstant(0)
declare v_idx = i4 with protect, noconstant(0)
declare code_val = f8 with protect, noconstant(uar_get_code_by("MEANING", 4, "MRN"))
declare applyfont(font_name = vc) = null

; Various string delimiters in CCL (backslash is literal, NOT an escape)
declare single_q = vc with protect, constant('\')
declare caret_str = vc with protect, constant(^Contains "double" and 'single' quotes^)
declare tilde_str = vc with protect, constant(~Contains ^carets^ and "quotes"~)

select into "nl:"
    p.person_id,
    p.name_full_formatted,
    formatted_dt = format(p.updt_dt_tm, ";;q")
from
    person p,
    code_value c1
plan p where p.active_ind = 1
    and p.person_id != 0.0
join c1 where p.sex_cd = c1.code_value
with format, separator=" ", time=60
go

for (v_idx = 1 to rs_dta_results->cnt)
    set raw_text_var = replace(raw_text_var, concat(char(13), char(10)), char(10), 0)
    set raw_text_var = trim(raw_text_var, 3)

    while (textlen(raw_text_var) > 0 and substring(1, 1, raw_text_var) in (" ", char(10)))
        if (textlen(raw_text_var) = 1)
            set raw_text_var = ""
        else
            set raw_text_var = substring(2, textlen(raw_text_var) - 1, raw_text_var)
        endif
    endwhile

    if (textlen(raw_text_var) > 0)
        ; Escape RTF control characters before passing to PRINTTEXT
        set raw_text_var = replace(raw_text_var, "\", "\\", 0)
        set raw_text_var = replace(raw_text_var, "{", "\{", 0)
        set raw_text_var = replace(raw_text_var, "}", "\}", 0)

        set rs_dta_results->list[v_idx].clean_text = raw_text_var
        set valid_output_cnt = valid_output_cnt + 1
    endif
endfor

if (valid_output_cnt > 0)
    call applyfont("NORMAL")
    set reply->text = build2("Processed ", cnvtstring(valid_output_cnt), " items")
endif

subroutine applyfont(font_name)
    call echo(build("Applying font: ", font_name))
end

end go
