# Confidential:
# (C) 2016 University of Bristol. See License.txt

import itertools, time
from collections import defaultdict, deque
from Compiler.exceptions import *
from Compiler.config import *
from Compiler.instructions import *
from Compiler.instructions_base import *
from Compiler.util import *
import Compiler.graph
import Compiler.program
import heapq, itertools
import operator


class StraightlineAllocator:
    """Allocate variables in a straightline program using n registers.
    It is based on the precondition that every register is only defined once."""
    def __init__(self, n):
        self.free = defaultdict(set)
        self.alloc = {}
        self.usage = Compiler.program.RegType.create_dict(lambda: 0)
        self.defined = {}
        self.dealloc = set()
        self.n = n

    def alloc_reg(self, reg, persistent_allocation):
        base = reg.vectorbase
        if base in self.alloc:
            # already allocated
            return

        reg_type = reg.reg_type
        size = base.size
        if not persistent_allocation and self.free[reg_type, size]:
            res = self.free[reg_type, size].pop()
        else:
            if self.usage[reg_type] < self.n:
                res = self.usage[reg_type]
                self.usage[reg_type] += size
            else:
                raise RegisterOverflowError()
        self.alloc[base] = res

        if base.vector:
            for i,r in enumerate(base.vector):
                r.i = self.alloc[base] + i
        else:
            base.i = self.alloc[base]

    def dealloc_reg(self, reg, inst):
        self.dealloc.add(reg)
        base = reg.vectorbase

        if base.vector and not inst.is_vec():
            for i in base.vector:
                if i not in self.dealloc:
                    # not all vector elements ready for deallocation
                    return
        self.free[reg.reg_type, base.size].add(self.alloc[base])
        if inst.is_vec() and base.vector:
            for i in base.vector:
                self.defined[i] = inst
        else:
            self.defined[reg] = inst

    def process(self, program, persistent_allocation=False):
        for k,i in enumerate(reversed(program)):
            unused_regs = []
            for j in i.get_def():
                if j.vectorbase in self.alloc:
                    if j in self.defined:
                        raise CompilerError("Double write on register %s " \
                                            "assigned by '%s' in %s" % \
                                                (j,i,format_trace(i.caller)))
                else:
                    # unused register
                    self.alloc_reg(j, persistent_allocation)
                    unused_regs.append(j)
            if unused_regs and len(unused_regs) == len(i.get_def()):
                # only report if all assigned registers are unused
                print "Register(s) %s never used, assigned by '%s' in %s" % \
                    (unused_regs,i,format_trace(i.caller))

            for j in i.get_used():
                self.alloc_reg(j, persistent_allocation)
            for j in i.get_def():
                self.dealloc_reg(j, i)

            if k % 1000000 == 0 and k > 0:
                print "Allocated registers for %d instructions at" % k, time.asctime()

        # print "Successfully allocated registers"
        # print "modp usage: %d clear, %d secret" % \
        #     (self.usage[Compiler.program.RegType.ClearModp], self.usage[Compiler.program.RegType.SecretModp])
        # print "GF2N usage: %d clear, %d secret" % \
        #     (self.usage[Compiler.program.RegType.ClearGF2N], self.usage[Compiler.program.RegType.SecretGF2N])
        return self.usage


def determine_scope(block):
    last_def = defaultdict(lambda: -1)
    used_from_scope = set()

    def find_in_scope(reg, scope):
        if scope is None:
            return False
        elif reg in scope.defined_registers:
            return True
        else:
            return find_in_scope(reg, scope.scope)

    def read(reg, n):
        if last_def[reg] == -1:
            if find_in_scope(reg, block.scope):
                used_from_scope.add(reg)
                reg.can_eliminate = False
            else:
                print 'Warning: read before write at register', reg
                print '\tline %d: %s' % (n, instr)
                print '\tinstruction trace: %s' % format_trace(instr.caller, '\t\t')
                print '\tregister trace: %s' % format_trace(reg.caller, '\t\t')

    def write(reg, n):
        if last_def[reg] != -1:
            print 'Warning: double write at register', reg
            print '\tline %d: %s' % (n, instr)
            print '\ttrace: %s' % format_trace(instr.caller, '\t\t')
        last_def[reg] = n

    for n,instr in enumerate(block.instructions):
        outputs,inputs = instr.get_def(), instr.get_used()
        for reg in inputs:
            if reg.vector and instr.is_vec():
                for i in reg.vector:
                    read(i, n)
            else:
                read(reg, n)
        for reg in outputs:
            if reg.vector and instr.is_vec():
                for i in reg.vector:
                    write(i, n)
            else:
                write(reg, n)

    block.used_from_scope = used_from_scope
    block.defined_registers = set(last_def.iterkeys())

class Merger:
    def __init__(self, block, options):
        self.block = block
        self.instructions = block.instructions
        self.options = options
        if options.max_parallel_open:
            self.max_parallel_open = int(options.max_parallel_open)
        else:
            self.max_parallel_open = float('inf')
        self.dependency_graph()

    def do_merge(self, merges_iter):
        """ Merge an iterable of nodes in G, returning the number of merged
        instructions and the index of the merged instruction. """
        instructions = self.instructions

        ### added for debug (start) ###
        # print(instructions)
        ### added for debug (start) ###

        mergecount = 0
        try:
            n = next(merges_iter)
            ### added for debug (start) ###
            # print("n:"+str(n))
            ### added for debug (ended) ###

        except StopIteration:
            return mergecount, None

        def expand_vector_args(inst):
            new_args = []
            for arg in inst.args:
                if inst.is_vec():
                    arg.create_vector_elements()
                    for reg in arg:
                        new_args.append(reg)
                else:
                    new_args.append(arg)
            return new_args

        Type_Different_flag = 0

        for i in merges_iter:

            ### added for debug (start) ###
            # print("n:")
            # print(n)
            # print('%d-th instructions[n];' % i)
            # print(instructions[n])
            # print('%d-th instructions[n].args;' % i)
            # print(instructions[n].args)
            # print("instructions[n] type;")
            # print(type(instructions[n]))
            # print('%d-th instructions[i];' % i)
            # print(instructions[i])
            # print('%d-th instructions[i].args;' % i)
            # print(instructions[i].args)
            # print("instructions[i] type;")
            # print(type(instructions[i]))
            ### added for debug (ended) ###

            if isinstance(instructions[n], startinput_class):
                ### added for debug (start) ###
                # print("test1")
                ### added for debug (ended) ###

                instructions[n].args[1] += instructions[i].args[1]

                ### added for debug (start) ###
                # print(self.instructions)
                ### added for debug (ended) ###
            elif isinstance(instructions[n], (startopen_class,stopopen_class)) and (type(instructions[n]) is not type(instructions[i])):
                ### added for debug (start) ###
                # print("check4")
                # print("type_of_instructions[n]:")
                # print(type(instructions[n]))
                # print("type_of_instructions[i]:")
                # print(type(instructions[i]))
                ### added for debug (ended) ###

                Type_Different_flag = 1

            elif isinstance(instructions[n], (stopinput, gstopinput)):
                if instructions[n].get_size() != instructions[i].get_size():
                    raise NotImplemented()
                else:
                    instructions[n].args += instructions[i].args[1:]

                    ### added for debug (start) ###
                    # print("test2")
                    ### added for debug (ended) ###
            else:
                if instructions[n].get_size() != instructions[i].get_size():
                    ### added for debug (start) ###
                    # print("test3")
                    ### added for debug (ended) ###

                    # merge as non-vector instruction
                    instructions[n].args = expand_vector_args(instructions[n]) + \
                        expand_vector_args(instructions[i])
                    if instructions[n].is_vec():
                        instructions[n].size = 1

                        ### added for debug (start) ###
                        # print("test4")
                        ### added for debug (ended) ###
                else:
                    ### added for debug (start) ###
                    # print("test5")
                    ### added for debug (ended) ###
                    instructions[n].args += instructions[i].args
                
            # join arg_formats if not special iterators
            # if not isinstance(instructions[n].arg_format, (itertools.repeat, itertools.cycle)) and \
            #     not isinstance(instructions[i].arg_format, (itertools.repeat, itertools.cycle)):
            #     instructions[n].arg_format += instructions[i].arg_format

            # instructions[i] = None

            # ADDED
            if Type_Different_flag == 0:
                instructions[i] = None
            else:
                Type_Different_flag = 0
            # ADDED END

            ### added for debug (start) ###
            # print("after instructions[i] = None: "+str(instructions))
            ### added for debug (ended) ###

            # self.merge_nodes(n, i)
            # mergecount += 1

            # ADDED
            if Type_Different_flag == 0:
                self.merge_nodes(n, i)
                mergecount += 1
            else:
                Type_Different_flag = 0
            # ADDED END

        return mergecount, n

    def compute_max_depths(self, depth_of):
        """ Compute the maximum 'depth' at which every instruction can be placed.
        This is the minimum depth of any merge_node succeeding an instruction.

        Similar to DAG shortest paths algorithm. Traverses the graph in reverse
        topological order, updating the max depth of each node's predecessors.
        """
        G = self.G
        merge_nodes_set = self.open_nodes
        top_order = Compiler.graph.topological_sort(G)
        max_depth_of = [None] * len(G)
        max_depth = max(depth_of)

        for i in range(len(max_depth_of)):
            if i in merge_nodes_set:
                max_depth_of[i] = depth_of[i] - 1
            else:
                max_depth_of[i] = max_depth

        for u in reversed(top_order):
            for v in G.pred[u]:
                if v not in merge_nodes_set:
                    max_depth_of[v] = min(max_depth_of[u], max_depth_of[v])
        return max_depth_of

    def merge_inputs(self):
        merges = defaultdict(list)
        remaining_input_nodes = []
        def do_merge(nodes):
            if len(nodes) > 1000:
                print 'Merging %d inputs...' % len(nodes)
            self.do_merge(iter(nodes))
        for n in self.input_nodes:
            inst = self.instructions[n]
            merge = merges[inst.args[0],inst.__class__]
            if len(merge) == 0:
                remaining_input_nodes.append(n)
            merge.append(n)
            if len(merge) >= self.max_parallel_open:
                do_merge(merge)
                merge[:] = []
        for merge in merges.itervalues():
            if merge:
                do_merge(merge)
        self.input_nodes = remaining_input_nodes

    def compute_preorder(self, merges, rev_depth_of):
        # find flexible nodes that can be on several levels
        # and find sources on level 0
        G = self.G
        merge_nodes_set = self.open_nodes
        depth_of = self.depths
        instructions = self.instructions
        flex_nodes = defaultdict(dict)
        starters = []
        for n in xrange(len(G)):
            if n not in merge_nodes_set and \
                depth_of[n] != rev_depth_of[n] and G[n] and G.get_attr(n,'start') == -1 and not isinstance(instructions[n], AsymmetricCommunicationInstruction):
                    #print n, depth_of[n], rev_depth_of[n]
                    flex_nodes[depth_of[n]].setdefault(rev_depth_of[n], set()).add(n)
            elif len(G.pred[n]) == 0 and \
                    not isinstance(self.instructions[n], RawInputInstruction):
                starters.append(n)
            if n % 10000000 == 0 and n > 0:
                print "Processed %d nodes at" % n, time.asctime()

        inputs = defaultdict(list)
        for node in self.input_nodes:
            player = self.instructions[node].args[0]
            inputs[player].append(node)
        first_inputs = [l[0] for l in inputs.itervalues()]
        other_inputs = []
        i = 0
        while True:
            i += 1
            found = False
            for l in inputs.itervalues():
                if i < len(l):
                    other_inputs.append(l[i])
                    found = True
            if not found:
                break
        other_inputs.reverse()

        preorder = []
        # magical preorder for topological search
        max_depth = max(merges)
        if max_depth > 10000:
            print "Computing pre-ordering ..."
        for i in xrange(max_depth, 0, -1):
            preorder.append(G.get_attr(merges[i], 'stop'))
            for j in flex_nodes[i-1].itervalues():
                preorder.extend(j)
            preorder.extend(flex_nodes[0].get(i, []))
            preorder.append(merges[i])
            if i % 100000 == 0 and i > 0:
                print "Done level %d at" % i, time.asctime()
        preorder.extend(other_inputs)
        preorder.extend(starters)
        preorder.extend(first_inputs)
        if max_depth > 10000:
            print "Done at", time.asctime()
        return preorder

    def compute_continuous_preorder(self, merges, rev_depth_of):
        print 'Computing pre-ordering for continuous computation...'
        preorder = []
        sources_for = defaultdict(list)
        stops_in = defaultdict(list)
        startinputs = []
        stopinputs = []
        for source in self.sources:
            sources_for[rev_depth_of[source]].append(source)
        for merge in merges.itervalues():
            stop = self.G.get_attr(merge, 'stop')
            stops_in[rev_depth_of[stop]].append(stop)
        for node in self.input_nodes:
            if isinstance(self.instructions[node], startinput_class):
                startinputs.append(node)
            else:
                stopinputs.append(node)
        max_round = max(rev_depth_of)
        for i in xrange(max_round, 0, -1):
            preorder.extend(reversed(stops_in[i]))
            preorder.extend(reversed(sources_for[i]))
        # inputs at the beginning
        preorder.extend(reversed(stopinputs))
        preorder.extend(reversed(sources_for[0]))
        preorder.extend(reversed(startinputs))
        return preorder

    def longest_paths_merge(self, instruction_type=startopen_class,
            merge_stopopens=True):
        """ Attempt to merge instructions of type instruction_type (which are given in
        merge_nodes) using longest paths algorithm.

        Returns the no. of rounds of communication required after merging (assuming 1 round/instruction).

        If merge_stopopens is True, will also merge associated stop_open instructions.
        If reorder_between_opens is True, will attempt to place non-opens between start/stop opens.

        Doesn't use networkx.

        Input:
            - self.G - ?
            - self.instruction - ?
            - self.open_nodes
            - self.depths - for every node, the depth
        """
        G = self.G
        instructions = self.instructions
        #print(instructions)
        merge_nodes = self.open_nodes
        #print(merge_nodes) hikaru_comment
        depths = self.depths
        #print(depths) hikaru_comment

        #checking that merge_stopopen only if merging start_open
        if instruction_type is not startopen_class and merge_stopopens:
            raise CompilerError('Cannot merge stopopens whilst merging %s instructions' % instruction_type)

        #if nothing to merger return - if we have only local instruction (clear instruction)
        if not merge_nodes and not self.input_nodes:
            return 0


        # merge opens at same depth
        merges = defaultdict(list)
        for node in merge_nodes:
            merges[depths[node]].append(node)

        ### added for debug (start) ###
        # print("merges:" + str(merges))
        ### added for debug (ended) ###

        # If you do not want to optimeze, return 0 at this point
        #return 0

        # after merging, the first element in merges[i] remains for each depth i,
        # all others are removed from instructions and G
        last_nodes = [None, None]
        for i in sorted(merges): # sorted(mergers): list of depth
            merge = merges[i]

            ### added for debug (start) ###
            # print("merge:"+str(merge))
            ### added for debug (ended) ###

            if len(merge) > 1000:
                print 'Merging %d opens in round %d/%d' % (len(merge), i, len(merges))
            nodes = defaultdict(lambda: None)
            #print("i;"+str(i))
            #print("check1;"+str(instructions))


            for b in (False, True):
                #my_merge = (m for m in merge if instructions[m] is not None and instructions[m].is_gf2n() is b)
                #my_merge = (m for m in merge if instructions[m] is not None and isinstance(instructions[m], e_startmult_class) is b)
                my_merge = (m for m in merge if instructions[m] is not None and isinstance(instructions[m], startopen_class) is b)
                #print("b;"+str(b))
                #print("check2;" + str(instructions))
                #print("[generator object]")
                #print([m for m in merge if instructions[m] is not None and isinstance(instructions[m], startopen_class) is b])
                if merge_stopopens:
                    #my_stopopen = [G.get_attr(m, 'stop') for m in merge if instructions[m] is not None and instructions[m].is_gf2n() is b]
                    #my_stopopen = [G.get_attr(m, 'stop') for m in merge if instructions[m] is not None and isinstance(instructions[m], e_startmult_class) is b]
                    my_stopopen = [G.get_attr(m, 'stop') for m in merge if instructions[m] is not None and isinstance(instructions[m], startopen_class) is b]

                    #print("test")
                    #print("check2.5;" + str(instructions))

                mc, nodes[0,b] = self.do_merge(iter(my_merge))

                #print("mc;")
                #print(mc)
                #print("nodes[0,{0}];".format(b))
                #print(nodes[0,b])
                #print("check2.8;" + str(instructions))
                #print("b;" + str(b))
                #print("check3;" + str(instructions))

                if merge_stopopens:
                    mc, nodes[1,b] = self.do_merge(iter(my_stopopen))

                    #print("mc;")
                    #print(mc)
                    #print("nodes[1,{0}];".format(b))
                    #print(nodes[1, b])

            # add edges to retain order of gf2n/modp start/stop opens
            for j in (0,1): #on all types - and add all edges
                node2 = nodes[j,True]
                nodep = nodes[j,False]
                if nodep is not None and node2 is not None:
                    G.add_edge(nodep, node2)
                # add edge to retain order of opens over rounds
                if last_nodes[j] is not None:
                    G.add_edge(last_nodes[j], node2 if nodep is None else nodep)
                last_nodes[j] = nodep if node2 is None else node2

                ### DEBUG (START) ###
                #print("last_nodes[{0}]:".format(j))
                #print(last_nodes[j])
                ### DEBUG (END) ###

            ### DEBUG (START) ###
            # print("befor replacing"+str(merges))
            ### DEBUG (END) ###

            merges[i] = last_nodes[0]

            ### DEBUG (START) ###
            # print("after replacing"+str(merges))
            ### DEBUG (END) ###

        self.merge_inputs()

        # compute preorder for topological sort
        if merge_stopopens and self.options.reorder_between_opens:
            if self.options.continuous or not merge_nodes:
                rev_depths = self.compute_max_depths(self.real_depths)
                preorder = self.compute_continuous_preorder(merges, rev_depths)
            else:
                rev_depths = self.compute_max_depths(self.depths)
                preorder = self.compute_preorder(merges, rev_depths)
        else:
            preorder = None

        if len(instructions) > 100000:
            print "Topological sort ..."
        order = Compiler.graph.topological_sort(G, preorder)
        instructions[:] = [instructions[i] for i in order if instructions[i] is not None]
        if len(instructions) > 100000:
            print "Done at", time.asctime()

        return len(merges)

    def extended_longest_paths_merge_4inst(self, instruction_type=startopen_class,
                            merge_stopopens=True):
        """ Attempt to merge instructions of type instruction_type (which are given in
        merge_nodes) using longest paths algorithm.

        Returns the no. of rounds of communication required after merging (assuming 1 round/instruction).

        If merge_stopopens is True, will also merge associated stop_open instructions.
        If reorder_between_opens is True, will attempt to place non-opens between start/stop opens.

        Doesn't use networkx.

        Input:
            - self.G - ?
            - self.instruction - ?
            - self.open_nodes
            - self.depths - for every node, the depth
        """

        ### Hikaru comment ###
        # The "extended_isinstance" returns true if the object argument is an instance of the class inheriting startopen_class.
        # It has been improved in terms of supporting not only modp but also gf2n.

        def extended_isinstance(object):
            value = 0
            if isinstance(object,e_startmult_class) and object.is_gf2n() is False:
                value = 0
            elif isinstance(object,startopen_class) and object.is_gf2n() is False:
                value = 1
            elif isinstance(object,e_startmult_class) and object.is_gf2n() is True:
                value = 2
            elif isinstance(object,startopen_class) and object.is_gf2n() is True:
                value = 3

            ### DEBUG (START) ###
            # print("class is:")
            # print(value)
            ### DEBUG (END) ###
            return value

        G = self.G
        instructions = self.instructions
        merge_nodes = self.open_nodes
        depths = self.depths

        ### added for debug (start) ###
        # print("depths:")
        # print(depths)
        ### added for debug (ended) ###

        # checking that merge_stopopen only if merging start_open
        if instruction_type is not startopen_class and merge_stopopens:
            raise CompilerError('Cannot merge stopopens whilst merging %s instructions' % instruction_type)

        # if nothing to merger return - if we have only local instruction (clear instruction)
        if not merge_nodes and not self.input_nodes:
            return 0

        # merge opens at same depth
        merges = defaultdict(list)
        for node in merge_nodes:
            merges[depths[node]].append(node)

        ### added for debug (start) ###
        print(merges)
        ### added for debug (ended) ###

        ### added for debug --- without optimization (start) ###
        # return 0
        ### added for debug --- without optimization (end) ###

        # after merging, the first element in merges[i] remains for each depth i,
        # all others are removed from instructions and G

        ### DEBUG (START) ###
        # print(merges)
        ### DEBUG (END) ###

        last_nodes = [None, None]
        for i in sorted(merges):  # sorted(mergers): list of depth
            merge = merges[i]

            ### added for debug (start) ###
            # print("merge:" + str(merge))
            ### added for debug (ended) ###

            if len(merge) > 1000:
                print 'Merging %d opens in round %d/%d' % (len(merge), i, len(merges))
            nodes = defaultdict(lambda: None)

            for b in (0, 1, 2, 3):

                ### added for debug (start) ###
                # print("b:")
                # print(b)
                ### added for debug (ended) ###

                my_merge = (m for m in merge if instructions[m] is not None and extended_isinstance(instructions[m]) is b)

                ### DEBUG (START) ###
                # print("[generator object]")
                # print([m for m in merge if instructions[m] is not None and extended_isinstance(instructions[m]) is b])
                ### DEBUG (END) ###

                if merge_stopopens:
                    my_stopopen = [G.get_attr(m, 'stop') for m in merge if
                                   instructions[m] is not None and extended_isinstance(instructions[m]) is b]

                mc, nodes[0, b] = self.do_merge(iter(my_merge))

                ### added for debug (start) ###
                # print("mc;")
                # print(mc)
                # print("nodes[0,{0}];".format(b))
                # print(nodes[0, b])
                ### added for debug (ended) ###

                if merge_stopopens:
                    mc, nodes[1, b] = self.do_merge(iter(my_stopopen))

                    ### added for debug (start) ###
                    # print("mc;")
                    # print(mc)
                    # print("nodes[1,{0}];".format(b))
                    # print(nodes[1, b])
                    ### added for debug (ended) ###

            # add edges to retain order of gf2n/modp start/stop opens
            for j in (0, 1):  # on all types - and add all edges
                node_count = 0
                tmp_node = None

                ### added for debug (start) ###
                # print("node_count_init:")
                # print(node_count)
                ### added for debug (ended) ###

                e_startmult_node = nodes[j, 0] # e_startmult

                ### added for debug (start) ###
                # print("node[{0}, 0]: {1}".format(j,nodes[j, 0]))
                ### added for debug (ended) ###

                if e_startmult_node is not None:
                    node_count += 1
                    tmp_node = e_startmult_node

                ### added for debug (start) ###
                # print("node_count_0:")
                # print(node_count)
                ### added for debug (ended) ###

                startopen_node = nodes[j, 1] # startopen

                ### added for debug (start) ###
                # print("node[{0}, 1]: {1}".format(j,nodes[j, 1]))
                ### added for debug (start) ###

                if startopen_node is not None:
                    node_count += 1
                    tmp_node = startopen_node

                ### added for debug (start) ###
                # print("node_count_1:")
                # print(node_count)
                ### added for debug (ended) ###

                ge_startmult_node = nodes[j, 2] # ge_startmult

                ### added for debug (start) ###
                # print("node[{0}, 2]: {1}".format(j,nodes[j, 2]))
                ### added for debug (ended) ###

                if ge_startmult_node is not None:
                    node_count += 1
                    tmp_node = ge_startmult_node

                ### added for debug (start) ###
                # print("node_count_2:")
                # print(node_count)
                ### added for debug (ended) ###

                gstartopen_node = nodes[j, 3] # gstartopen

                ### added for debug (start) ###
                # print("node[{0}, 3]: {1}".format(j,nodes[j, 3]))
                ### added for debug (ended) ###

                if gstartopen_node is not None:
                    node_count += 1
                    tmp_node = gstartopen_node

                ### added for debug (start) ###
                # print("node_count_res:")
                # print(node_count)
                ### added for debug (ended) ###

                if node_count == 2:
                    if e_startmult_node is not None and startopen_node is not None:
                        G.add_edge(e_startmult_node, startopen_node)
                        tmp_node = e_startmult_node
                    elif e_startmult_node is not None and ge_startmult_node is not None:
                        G.add_edge(e_startmult_node, ge_startmult_node)
                        tmp_node = e_startmult_node
                    elif e_startmult_node is not None and gstartopen_node is not None:
                        G.add_edge(e_startmult_node, gstartopen_node)
                        tmp_node = e_startmult_node
                    elif startopen_node is not None and ge_startmult_node is not None:
                        G.add_edge(startopen_node, ge_startmult_node)
                        tmp_node = startopen_node
                    elif startopen_node is not None and gstartopen_node is not None:
                        G.add_edge(startopen_node, gstartopen_node)
                        tmp_node = startopen_node
                    elif ge_startmult_node is not None and gstartopen_node is not None:
                        G.add_edge(ge_startmult_node, gstartopen_node)
                        tmp_node = ge_startmult_node
                elif node_count == 3:
                    if e_startmult_node is not None and startopen_node is not None and ge_startmult_node is not None:
                        G.add_edge(e_startmult_node, startopen_node)
                        G.add_edge(e_startmult_node, ge_startmult_node)
                        tmp_node = e_startmult_node
                    elif e_startmult_node is not None and startopen_node is not None and gstartopen_node is not None:
                        G.add_edge(e_startmult_node, startopen_node)
                        G.add_edge(e_startmult_node, gstartopen_node)
                        tmp_node = e_startmult_node
                    elif e_startmult_node is not None and ge_startmult_node is not None and gstartopen_node is not None:
                        G.add_edge(e_startmult_node, ge_startmult_node)
                        G.add_edge(e_startmult_node, gstartopen_node)
                        tmp_node = e_startmult_node
                    elif startopen_node is not None and ge_startmult_node is not None and gstartopen_node is not None:
                        G.add_edge(startopen_node, ge_startmult_node)
                        G.add_edge(startopen_node, gstartopen_node)
                        tmp_node = startopen_node
                elif node_count == 4:
                    G.add_edge(e_startmult_node, startopen_node)
                    G.add_edge(e_startmult_node, ge_startmult_node)
                    G.add_edge(e_startmult_node, gstartopen_node)
                    tmp_node = e_startmult_node

                # add edge to retain order of opens over rounds
                if last_nodes[j] is not None:
                    if node_count == 0:
                        pass
                    else:
                        G.add_edge(last_nodes[j], tmp_node)

                last_nodes[j] = tmp_node
            merges[i] = last_nodes[0]

            ### added for debug (start) ###
            # print("merges[depth]:" + str(merges[i]))
            # print("merges:"+str(merges))
            ### added for debug (ended) ###

        self.merge_inputs()

        # compute preorder for topological sort
        if merge_stopopens and self.options.reorder_between_opens:
            if self.options.continuous or not merge_nodes:
                rev_depths = self.compute_max_depths(self.real_depths)
                preorder = self.compute_continuous_preorder(merges, rev_depths)
            else:
                rev_depths = self.compute_max_depths(self.depths)
                preorder = self.compute_preorder(merges, rev_depths)
        else:
            preorder = None

        if len(instructions) > 100000:
            print "Topological sort ..."
        order = Compiler.graph.topological_sort(G, preorder)
        instructions[:] = [instructions[i] for i in order if instructions[i] is not None]

        ### added for debug (start) ###
        # print(instructions)
        ### added for debug (ended) ###

        if len(instructions) > 100000:
            print "Done at", time.asctime()

        return len(merges)

    def dependency_graph(self, merge_class=startopen_class):
        """ Create the program dependency graph. """
        block = self.block

        ### DEBUG (START) ###
        # print("self.block:")
        # print(block)
        ### DEBUG (END) ###

        options = self.options
        open_nodes = set()
        self.open_nodes = open_nodes
        self.input_nodes = []
        colordict = defaultdict(lambda: 'gray', startopen='red', stopopen='red',\
                                ldi='lightblue', ldm='lightblue', stm='blue',\
                                mov='yellow', mulm='orange', mulc='orange',\
                                triple='green', square='green', bit='green',\
                                asm_input='lightgreen')

        G = Compiler.graph.SparseDiGraph(len(block.instructions))
        self.G = G

        reg_nodes = {}
        last_def = defaultdict(lambda: -1)

        ### DEBUG (START) ###
        # print("last_def:")
        # print(last_def)
        ### DEBUG (END) ###

        last_mem_write = []
        last_mem_read = []
        warned_about_mem = []
        last_mem_write_of = defaultdict(list)
        last_mem_read_of = defaultdict(list)
        last_print_str = None
        last = defaultdict(lambda: defaultdict(lambda: None))
        last_open = deque()

        depths = [0] * len(block.instructions)
        self.depths = depths

        ### DEBUG (START) ###
        # print("In dependency_graph, depth:")
        # print(depths)
        ### DEBUG (END) ###

        parallel_open = defaultdict(lambda: 0)
        next_available_depth = {}
        self.sources = []
        self.real_depths = [0] * len(block.instructions)

        ### DEBUG (START) ###
        # print("In dependency_graph, real_depth:")
        # print(self.real_depths)
        ### DEBUG (END) ###

        def add_edge(i, j):
            from_merge = isinstance(block.instructions[i], merge_class)
            to_merge = isinstance(block.instructions[j], merge_class)
            G.add_edge(i, j)
            is_source = G.get_attr(i, 'is_source') and G.get_attr(j, 'is_source') and not from_merge
            G.set_attr(j, 'is_source', is_source)
            for d in (self.depths, self.real_depths):

                ### DEBUG (START) ###
                # print("before add_edge; self.depths:")
                # print(self.depths)
                # print("before add_edge; self.real_depths:")
                # print(self.real_depths)
                ### DEBUG (START) ###

                if d[j] < d[i]:
                    d[j] = d[i]

                ### DEBUG (START) ###
                # print("after add_edge; self.depths:")
                # print(self.depths)
                # print("after add_edge; self.real_depths:")
                # print(self.real_depths)
                ### DEBUG (START) ###

        def read(reg, n):

            ### DEBUG (START) ###
            # print("reg (read):")
            # print(reg)
            # print("last_def (before read):")
            # print(last_def)
            ### DEBUG (END) ###

            if last_def[reg] != -1:
                add_edge(last_def[reg], n)

        def write(reg, n):

            ### DEBUG (START) ###
            # print("n (write):")
            # print(n)
            # print("reg (write):")
            # print(reg)
            # print("last_def (before write):")
            # print(last_def)
            ### DEBUG (START) ###

            last_def[reg] = n

            ### DEBUG (START) ###
            # print("last_def (after write):")
            # print(last_def)
            ### DEBUG (END) ###

        def handle_mem_access(addr, reg_type, last_access_this_kind,
                              last_access_other_kind):
            this = last_access_this_kind[addr,reg_type]
            other = last_access_other_kind[addr,reg_type]
            if this and other:
                if this[-1] < other[0]:
                    del this[:]
            this.append(n)
            for inst in other:
                add_edge(inst, n)

        def mem_access(n, instr, last_access_this_kind, last_access_other_kind):
            addr = instr.args[1]
            reg_type = instr.args[0].reg_type
            if isinstance(addr, int):
                for i in range(min(instr.get_size(), 100)):
                    addr_i = addr + i
                    handle_mem_access(addr_i, reg_type, last_access_this_kind,
                                      last_access_other_kind)
                if not warned_about_mem and (instr.get_size() > 100):
                    print 'WARNING: Order of memory instructions ' \
                        'not preserved due to long vector, errors possible'
                    warned_about_mem.append(True)
            else:
                handle_mem_access(addr, reg_type, last_access_this_kind,
                                  last_access_other_kind)
            if not warned_about_mem and not isinstance(instr, DirectMemoryInstruction):
                print 'WARNING: Order of memory instructions ' \
                    'not preserved, errors possible'
                # hack
                warned_about_mem.append(True)

        def keep_order(instr, n, t, arg_index=None):
            if arg_index is None:
                player = None
            else:
                player = instr.args[arg_index]
            if last[t][player] is not None:
                add_edge(last[t][player], n)
            last[t][player] = n

        for n,instr in enumerate(block.instructions):
            outputs,inputs = instr.get_def(), instr.get_used()

            ### DEBUG (START) ###
            # print("n:")
            # print(n)
            # print("instr:")
            # print(instr)
            # print("outputs:")
            # print(outputs)
            # print("inputs:")
            # print(inputs)
            ### DEBUG (END) ###

            G.add_node(n, is_source=True)

            # if options.debug:
            #     col = colordict[instr.__class__.__name__]
            #     G.add_node(n, color=col, label=str(instr))

            ### DEBUG (START) ###
            # print("read n-th instruction (inputs):")
            # print(n)
            ### DEBUG (END) ###

            for reg in inputs:
                if reg.vector and instr.is_vec():

                    ### DEBUG (START) ###
                    # print("if-branch (read):")
                    ### DEBUG (END) ###

                    for i in reg.vector:
                        ### DEBUG (START) ###
                        # print("i:")
                        # print(i)
                        ### DEBUG (END) ###

                        read(i, n)
                else:
                    ### DEBUG (START) ###
                    # print("else-branch (inputs)")
                    # print("reg:")
                    # print(reg)
                    ### DEBUG (END) ###

                    read(reg, n)

            ### DEBUG (START) ###
            # print("write n-th instruction (outputs):")
            # print(n)
            ### DEBUG (END) ###

            for reg in outputs:
                if reg.vector and instr.is_vec():
                    for i in reg.vector:
                        write(i, n)
                else:
                    write(reg, n)

            if isinstance(instr, merge_class):
                ### DEBUG (START) ###
                # print("n-th instruction of merge_class:")
                # print(n)
                # print(instr)
                ### DEBUG (END) ###

                open_nodes.add(n)

                ### DEBUG (START) ###
                # print("open_nodes:")
                # print(open_nodes)
                ### DEBUG (END) ###

                last_open.append(n)

                ### DEBUG (START) ###
                # print("last_open:")
                # print(last_open)
                ### DEBUG (END) ###

                G.add_node(n, merges=[])

                # the following must happen after adding the edge

                ### DEBUG (START) ###
                # print("before real_depths:")
                # print(self.real_depths)
                ### DEBUG (END) ###

                self.real_depths[n] += 1

                ### DEBUG (START) ###
                # print("after real_depths:")
                # print(self.real_depths)
                # print("depths:")
                # print(depths)
                ### DEBUG (END) ###

                depth = depths[n] + 1

                ### DEBUG (START) ###
                # print("after depth:")
                # print(depth)
                ### DEBUG (END) ###

                if int(options.max_parallel_open):
                    skipped_depths = set()
                    while parallel_open[depth] >= int(options.max_parallel_open):
                        skipped_depths.add(depth)
                        depth = next_available_depth.get(depth, depth + 1)
                    for d in skipped_depths:
                        next_available_depth[d] = depth
                parallel_open[depth] += len(instr.args) * instr.get_size()

                ### DEBUG (START) ###
                # print("parallel_open;{0}".format(parallel_open))
                ### DEBUG (END) ###

                depths[n] = depth

            if isinstance(instr, stopopen_class):
                ### DEBUG (START) ###
                # print("stop n-th instruction:")
                # print(n)
                # print("last_open before popleft:")
                # print(last_open)
                ### DEBUG (END) ###

                startopen = last_open.popleft()

                ### DEBUG (START) ###
                # print("startopen:")
                # print(startopen)
                # print("last_open after popleft")
                # print(last_open)
                # print("add_edge n-th instruction:")
                # print(n)
                ### DEBUG (END) ###

                add_edge(startopen, n)
                G.set_attr(startopen, 'stop', n)
                G.set_attr(n, 'start', last_open)
                G.add_node(n, merges=[])

            if isinstance(instr, ReadMemoryInstruction):
                if options.preserve_mem_order:
                    if last_mem_write and last_mem_read and last_mem_write[-1] > last_mem_read[-1]:
                        last_mem_read[:] = []
                    last_mem_read.append(n)
                    for i in last_mem_write:
                        add_edge(i, n)
                else:
                    mem_access(n, instr, last_mem_read_of, last_mem_write_of)
            elif isinstance(instr, WriteMemoryInstruction):
                if options.preserve_mem_order:
                    if last_mem_write and last_mem_read and last_mem_write[-1] < last_mem_read[-1]:
                        last_mem_write[:] = []
                    last_mem_write.append(n)
                    for i in last_mem_read:
                        add_edge(i, n)
                else:
                    mem_access(n, instr, last_mem_write_of, last_mem_read_of)
            # keep I/O instructions in order
            elif isinstance(instr, IOInstruction):
                if last_print_str is not None:
                    add_edge(last_print_str, n)
                last_print_str = n
            elif isinstance(instr, PublicFileIOInstruction):
                keep_order(instr, n, instr.__class__)
            elif isinstance(instr, RawInputInstruction):
                keep_order(instr, n, instr.__class__, 0)
                self.input_nodes.append(n)
                G.add_node(n, merges=[])
                player = instr.args[0]
                if isinstance(instr, stopinput):
                    add_edge(last[startinput_class][player], n)
                elif isinstance(instr, gstopinput):
                    add_edge(last[gstartinput][player], n)
            elif isinstance(instr, startprivateoutput_class):
                keep_order(instr, n, startprivateoutput_class, 2)
            elif isinstance(instr, stopprivateoutput_class):
                keep_order(instr, n, stopprivateoutput_class, 1)
            elif isinstance(instr, prep_class):
                keep_order(instr, n, instr.args[0])
            elif isinstance(instr, StackInstruction):
                keep_order(instr, n, StackInstruction)

            if not G.pred[n]:
                self.sources.append(n)

            if n % 100000 == 0 and n > 0:
                print "Processed dependency of %d/%d instructions at" % \
                    (n, len(block.instructions)), time.asctime()

        if len(open_nodes) > 1000:
            print "Program has %d %s instructions" % (len(open_nodes), merge_class)

    def merge_nodes(self, i, j):
        """ Merge node j into i, removing node j """
        G = self.G
        if j in G[i]:
            G.remove_edge(i, j)
        if i in G[j]:
            G.remove_edge(j, i)
        G.add_edges_from(zip(itertools.cycle([i]), G[j], [G.weights[(j,k)] for k in G[j]]))
        G.add_edges_from(zip(G.pred[j], itertools.cycle([i]), [G.weights[(k,j)] for k in G.pred[j]]))
        G.get_attr(i, 'merges').append(j)
        G.remove_node(j)

    def eliminate_dead_code(self):
        instructions = self.instructions
        G = self.G
        merge_nodes = self.open_nodes
        count = 0
        open_count = 0
        for i,inst in zip(xrange(len(instructions) - 1, -1, -1), reversed(instructions)):
            # remove if instruction has result that isn't used
            unused_result = not G.degree(i) and len(inst.get_def()) \
                and reduce(operator.and_, (reg.can_eliminate for reg in inst.get_def())) \
                and not isinstance(inst, (DoNotEliminateInstruction))
            stop_node = G.get_attr(i, 'stop')
            unused_startopen = stop_node != -1 and instructions[stop_node] is None
            if unused_result or unused_startopen:
                G.remove_node(i)
                merge_nodes.discard(i)
                instructions[i] = None
                count += 1
                if unused_startopen:
                    open_count += len(inst.args)
        if count > 0:
            print 'Eliminated %d dead instructions, among which %d opens' % (count, open_count)

    def print_graph(self, filename):
        f = open(filename, 'w')
        print >>f, 'digraph G {'
        for i in range(self.G.n):
            for j in self.G[i]:
                print >>f, '"%d: %s" -> "%d: %s";' % \
                    (i, self.instructions[i], j, self.instructions[j])
        print >>f, '}'
        f.close()

    def print_depth(self, filename):
        f = open(filename, 'w')
        for i in range(self.G.n):
            print >>f, '%d: %s' % (self.depths[i], self.instructions[i])
        f.close()
