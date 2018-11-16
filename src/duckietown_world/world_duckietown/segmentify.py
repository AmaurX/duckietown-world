from collections import namedtuple, defaultdict

from duckietown_world.geo import PlacedObject, SE2Transform
from duckietown_world.geo.measurements_utils import iterate_by_class


import numpy as np

from .lane_segment import LaneSegment


import geometry as geo


SkeletonGraphResult = namedtuple('SkeletonGraphResult', 'root root2 G')

def get_skeleton_graph(po):
    """ Returns a graph with the lane segments of the map """

    # Get all the LaneSegments

    root = PlacedObject()

    class MeetingPoint(object):
        def __init__(self):
            self.incoming = set()
            self.outcoming = set()

        def __repr__(self):
            return 'MP(%d %d | %s, %s)' % (len(self.incoming), len(self.outcoming), self.incoming, self.outcoming)

    def discretize(tran):
        def D(x):
            return np.round(x, decimals=2)

        p, theta = geo.translation_angle_from_SE2(tran.as_SE2())
        return D(p[0]), D(p[1]), D(np.cos(theta)), D(np.sin(theta))

    meeting_points = defaultdict(MeetingPoint)

    for i, it in enumerate(iterate_by_class(po, LaneSegment)):
        lane_segment = it.object
        # lane_segment_fqn = it.fqn
        assert isinstance(lane_segment, LaneSegment), lane_segment
        absolute_pose = it.transform_sequence.asmatrix2d()

        lane_segment_transformed = transform_lane_segment(lane_segment, absolute_pose)

        identity = SE2Transform.identity()
        name = 'ls%03d' % i
        root.set_object(name, lane_segment_transformed, ground_truth=identity)

        p0 = discretize(lane_segment_transformed.control_points[0])
        p1 = discretize(lane_segment_transformed.control_points[-1])

        meeting_points[p0].outcoming.add(name)
        meeting_points[p1].incoming.add(name)

    print(meeting_points)

    for k, mp in meeting_points.items():
        if (len(mp.incoming) == 0) or (len(mp.outcoming) == 0):
            msg = 'Completeness assumption violated at point %s: %s' % (k, mp)
            raise Exception(msg)

    # compress the lanes which are contiguous

    aliases = {}

    created = {}

    for k, mp in meeting_points.items():
        # continue
        if len(mp.incoming) == 1 and len(mp.outcoming) == 1:

            lin_name = list(mp.incoming)[0]
            lout_name = list(mp.outcoming)[0]

            def resolve_alias(x):
                return x if x not in aliases else resolve_alias(aliases[x])

            lin_name = resolve_alias(lin_name)
            lout_name = resolve_alias(lout_name)
            # print(' -> %s and %s meet at %s' % (lin_name, lout_name, mp))
            print('%s and %s meet at %s' % (lin_name, lout_name, k))

            def get(it):
                if it in root.children:
                    return root.children[it]
                else:
                    return created[it]

            lin = get(lin_name)
            lout = get(lout_name)

            # name = 'alias%s' % (len(aliases))
            name = '%s-%s' % (lin_name, lout_name)
            width = lin.width
            print(lin.control_points)
            print(lout.control_points)
            control_points = lin.control_points + lout.control_points[1:]
            ls = LaneSegment(width=width, control_points=control_points)
            created[name] = ls

            aliases[lin_name] = name
            aliases[lout_name] = name
            print('new alias %s' % name)

    print('created: %s' % list(created))
    print('aliases: %s' % aliases)
    root2 = PlacedObject()
    for k, v in created.items():
        if not k in aliases:
            root2.set_object(k, v, ground_truth=SE2Transform.identity())
            pass
    for k, v in root.children.items():
        if not k in aliases:
            root2.set_object(k, v, ground_truth=SE2Transform.identity())

    return SkeletonGraphResult(root=root, root2=root2, G=None)


def transform_lane_segment(lane_segment, transformation):
    M = transformation.m

    def transform_point(p):
        q = p.as_SE2()
        q2 = np.dot(M, q)
        p2 = SE2Transform.from_SE2(q2)
        return p2

    control_points = list(map(transform_point, lane_segment.control_points))

    det = np.linalg.det(M)
    width = float(lane_segment.width * np.sqrt(det))
    return LaneSegment(control_points=control_points, width=width)
