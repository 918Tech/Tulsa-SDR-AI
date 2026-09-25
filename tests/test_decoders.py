from tulsa_sdr_ai.decoders import DMRAdapter, OP25Adapter

def test_op25_patterns():
    lines=["talkgroup 1001","TGID=1002","grpaddr: 1003"]
    values=[]
    for line in lines:
        for p in OP25Adapter.patterns:
            m=p.search(line)
            if m:
                values.append(int(m.group(1)));break
    assert values==[1001,1002,1003]

def test_dmr_parser():
    d=DMRAdapter(["decoder","{frequency}"])
    assert d.parse_line("Talkgroup: 3101 slot 1")==3101
    assert d.build_command(serial="A",frequency_hz=856112500)==["decoder","856112500"]
